#!/usr/bin/env python
import json
import os
import requests

def send_trigger_request(email, TRAVIS_TAG, event_url, TRAVIS_SCRIPT, recipe, processor, feature):
    USER = 'fossasia'
    PROJECT = 'meilix'
    BRANCH = 'master'
    softwares = json.dumps(recipe) # This solves `unbound variable`(ISSUE #405)
    feature = json.dumps(feature)
    travis_api_url = 'https://api.travis-ci.org/repo/{}%2F{}/requests'.format(USER, PROJECT)
    request_body = {}
    request = {}
    request['branch'] = BRANCH
    request['config'] = {}
    request['config']['env'] = {}
    request['config']['env']['email'] = email
    request['config']['env']['TRAVIS_TAG'] = TRAVIS_TAG
    request['config']['env']['event_url'] = event_url
    request['config']['env']['TRAVIS_SCRIPT'] = TRAVIS_SCRIPT
    request['config']['env']['recipe'] = softwares
    request['config']['env']['processor'] = processor
    request['config']['env']['feature'] = feature
    request_body['request'] = request
    request_body = json.dumps(request_body)
    headers = { "Content-Type": "application/json", "Accept": "application/json", "Travis-API-Version": "3", "Authorization": "token {}".format(os.environ.get('KEY', None))}

    response = requests.post(travis_api_url, headers=headers, data=request_body)

    if response.status_code == 202:
        print('Trigger successful')
    else:
        print('Trigger failed, response code {}'.format(response.status_code))
    return(response.status_code)

