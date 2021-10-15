import hunger as h
import hunger_gui as hg
from waitress import serve
import webbrowser
import urllib.request

def getPort():
    return 8050
    
def getURL():
    ip = "localhost"
    with urllib.request.urlopen('http://api.ipify.org') as response:
        ip = response.read().decode('utf-8')
    return ip

def launchServer():
    #webbrowser.open("localhost:{}".format(getPort()))
    webbrowser.open("http://localhost:{}".format(getPort()))
    serve(hg.app.server, host='0.0.0.0', port=getPort())
    
launchServer()