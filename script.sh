#!/bin/bash
cat travis_tokens | while read line;
do
    array=(${line})
    user="${array[0]}"
    project="${array[1]}"
    len=${#array[@]}
    for ((i=2; i<len; i++)); do
        branch="${array[i]}"
        body="{\"request\":{
            \"branch\":\"${branch}\",
            \"config\":{
                \"env\":{
                    \"email\":\"${email}\",
                    \"TRAVIS_TAG\":\"${TRAVIS_TAG}\"
                }
            }
    }}"
    echo "This link will be ready in approx 20 minutes"

    echo "https://github.com/xeon-zolt/meilix/releases/download/${TRAVIS_TAG}/meilix-zesty-`date +%Y%m%d`-i386.iso"
    echo "Sending Data To travis To build ISO"
        curl -s -X POST \
            -H "Content-Type: application/json" \
            -H "Accept: application/json" \
            -H "Travis-API-Version: 3" \
            -H "Authorization: token ${KEY}" \
            -d "${body}" \
            "https://api.travis-ci.org/repo/${user}%2F${project}/requests"
    done
done
python3 url_test.py
