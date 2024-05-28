import os, time, ssl, wifi, socketpool, adafruit_requests, json
import board
import busio
import adafruit_mma8451
import pwmio
import neopixel
import digitalio

#initialisation des pins pour la carte d'adaptation de puissance du moteur pas à pas
IN1 = digitalio.DigitalInOut(board.GP15)
IN2 = digitalio.DigitalInOut(board.GP14)
IN3 = digitalio.DigitalInOut(board.GP16)
IN4 = digitalio.DigitalInOut(board.GP17)

#initialisation des paramètres necessaires à la led et au buzzer du maker
led_num = 1
BRIGHTNESS = 1.0  # Adjust the brightness (0.0 - 1.0)
neoRing = neopixel.NeoPixel((board.GP28), led_num)
buzzer_pin = board.GP18
buzzer_pwm = pwmio.PWMOut(buzzer_pin, frequency=500, duty_cycle=0)

#paramètres necessaires au fonctionnement de l'acceleromètre
i2c = busio.I2C(board.GP1, board.GP0)
sensor = adafruit_mma8451.MMA8451(i2c)

#fonction qui recupère l'heure irl grace à l'API WorldTimeAPI
def recupTime():
    #log in
    connect()

    pool = socketpool.SocketPool(wifi.radio)
    #creer un objet pour que la requête de données web soit possible
    requests = adafruit_requests.Session(pool, ssl.create_default_context())

    #url de l'API
    url = "https://worldtimeapi.org/api/timezone/"
    timezone = "Europe/Paris"
    url = url + timezone

    response = requests.get(url)

    # Analyser la réponse JSON de l'API
    data = json.loads(response.text)

    # Extraire le temps de la réponse
    date = data["datetime"]
    
    #formater afin de l'utiliser
    time = date.split("T")[1].split(":")[:3]
    h = time[0]
    m = time[1]
    return h,m

#fonction necessaire à l'allumage de la led neopixel du maker
def set_brightness(color):
    r, g, b = color
    r = int(r * BRIGHTNESS)
    g = int(g * BRIGHTNESS)
    b = int(b * BRIGHTNESS)
    return (r, g, b)

#fonction qui fait tourner le moteur d'un quart de tour
def tourne():
    pins = [IN1, IN2, IN3, IN4]
    sequence = [[1, 0, 0, 0], [0, 1, 0, 0], [0, 0, 1, 0], [0, 0, 0, 1]]
    for i in range(128):
        for step in sequence:
            for i in range(len(pins)):
                pins[i].switch_to_output()  # Définir la broche comme sortie
                pins[i].value = step[i]  # Définir l'état de la broche
                time.sleep(0.001)

#fonction coeur qui, à l'heure donné en paramètre, fait tourner le moteur d'un quart de tour puis fait sonner le buzzer et allume la led du maker
def cestlheure(heure, minute):
    #alarme=30 #minutes au bout desquelles l'alarme se declanche, non implémenté
    #urgence=False defini un statu d'urgence(en cas de non prise), non implémenté
    tour_effectue = False 
    while True:
        x, y, z = sensor.acceleration #
        orientation = sensor.orientation
        # Récupérer les heures et les minutes reel
        h,m = recupTime()
        print(h,m) #debogage
        if int(heure) == int(h) and int(minute) == int(m):
            #faire tourner le moteur
            if not tour_effectue:
                tourne()
                tour_effectue=True
            buzzer_pwm.duty_cycle = 52768
            color = (255, 0, 0)  # Rouge
            color = set_brightness(color)
            neoRing.fill(color)
            neoRing.write()
            #si à l'endroit alors ça sonne
            if (orientation == adafruit_mma8451.PL_PUF or orientation == adafruit_mma8451.PL_PDF or orientation == adafruit_mma8451.PL_LRF or orientation == adafruit_mma8451.PL_LLF):
                buzzer_pwm.duty_cycle = 52768
                color = (255, 0, 0)  
                color = set_brightness(color)
                neoRing.fill(color)
                neoRing.write()
            #il a été retourné : ça s'arrete de sonner
            else :
                buzzer_pwm.duty_cycle = 0
                color = (0, 0, 0)  # Rouge
                color = set_brightness(color)
                neoRing.fill(color)
                neoRing.write()
                break
            
# Connecter au Wi-Fi
def connect():
    #vles info d'authentification sont dans le fichier "settings.toml"
    wifi.radio.connect(os.getenv("WIFI_SSID"), os.getenv("WIFI_PASSWORD"))
    while not wifi.radio.ipv4_address:
        print("Waiting for connection...")
        time.sleep(1)
    #recuperer l'addresse ip pour la connexion au serveur web
    ip = wifi.radio.ipv4_address
    print(f'Connected on {ip}')
    return str(ip)

# Ouvrir un socket pour le serveur
def open_socket(ip):
    pool = socketpool.SocketPool(wifi.radio)
    address = (ip, 80)
    server = pool.socket(pool.AF_INET, pool.SOCK_STREAM)
    server.setsockopt(pool.SOL_SOCKET, pool.SO_REUSEADDR, 1)
    server.bind(address)
    server.listen(1)
    return server

# Page HTML
def webpage(state):
    html = f"""
            <!DOCTYPE html>
<html>
  <body>
    <form action="/" method="GET">
      <label for="morning">Matin:</label>
      <input type="text" name="morning" id="morning" placeholder="Enter time for morning (hh mm)"><br><br>
      
      <label for="noon">Midi:</label>
      <input type="text" name="noon" id="noon" placeholder="Enter time for noon (hh mm)"><br><br>
      
      <label for="evening">Soir:</label>
      <input type="text" name="evening" id="evening" placeholder="Enter time for evening (hh mm)"><br><br>
      
      <label for="night">Nuit:</label>
      <input type="text" name="night" id="night" placeholder="Enter time for night (hh mm)"><br><br>
      
      <input type="submit" value="Set Times">
    </form>
    <p>{state}</p>
  </body>
</html>
            """
    return html

# Serve le web server
def serve(server):
    state = False
    #buffer pour recuperer la reponse du client
    buffer = bytearray(1024)

    while True:
        #accepter la connexion
        client, addr = server.accept()
        print(f"Client connected from {addr}")
        size = client.recv_into(buffer)
        request = str(buffer[:size], 'utf-8')
        try:
            path = request.split(' ')[1]
            print(path) #debogage
        except IndexError:
            continue

        #extraire les informations necessaires dans la requête
        if path.startswith('/?'):
            # Extraire l'heure de la "query string" (requête de type string)
            query = path.split('?')[1]
            query_params = query.split('&')
            times = {}  # Dictionnaire pour stocker les horaires
            for param in query_params:
                key, value = param.split('=')
                times[key] = value.replace('+', ' ')
            #un dictionnaire `times` contenant les horaires pour chaque moment de la journée
            matin = times.get('morning', '')
            midi = times.get('noon', '')
            soir = times.get('evening', '')
            nuit = times.get('night', '')
            print("matin", matin)
            print("midi", midi)
            print("soir", soir)
            print("nuit", nuit)
            
            h,m = recupTime()
            h_matin,m_matin=matin.split()[0],matin.split()[1]
            h_midi,m_midi=midi.split()[0],midi.split()[1]
            h_soir,m_soir=soir.split()[0],soir.split()[1]
            h_nuit,m_nuit=nuit.split()[0],nuit.split()[1]
#             
            cestlheure(h_matin,m_matin)
            cestlheure(h_midi,m_midi)
#           cestlheure(h_soir,m_soir)
#           cestlheure(h_nuit,m_nuit)
            
            
            
            
        #envoyer la reponse (la page web au clien)
        response = webpage(state)
        client.send("HTTP/1.1 200 OK\n")
        client.send("Content-Type: text/html\n")
        client.send("Connection: close\n\n")
        client.sendall(response)
        client.close()



try:
    ip = connect()
    server = open_socket(ip)
    serve(server)
except KeyboardInterrupt:
    print("Server stopped")