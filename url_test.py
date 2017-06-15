#!/usr/bin/python3

import os
import threading
import datetime
import requests


def status():
    """ Returns the progress of build url """
    s = threading.Timer(60.0, status)
    tag = os.environ["TRAVIS_TAG"]
    date = datetime.datetime.now().strftime('%Y%m%d')
    url = "https://github.com/xeon-zolt/meilix/releases/download/"+tag+"/meilix-zesty-"+date+"-i386.iso"
    s.start()
    try:
        req = requests.head(url)
        if req.status_code == 200:
            print('Build Sucessfull')
            print(url)
            s.cancel()
        elif req.status_code == 404:
            print('ISO is Building')
        else:
            print('Unable to reach to server')
    except requests.ConnectionError:
        print('Failed To Connect')


status()
