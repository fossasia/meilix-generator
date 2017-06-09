#!/bin/bash
cat travis_tokens | while read line;
do
    array=(${line})
    user="${array[0]}"
    project="${array[1]}"
    len=${#array[@]}
    for ((i=2; i<len; i++)); do
        branch="${array[i]}"
        body="{\"request\": {\"branch\":\"${branch}\"}}"
        echo "Triggering build of ${user}'s ${project}/${branch}
        curl -s -X POST \
            -H "Content-Type: application/json" \
            -H "Accept: application/json" \
            -H "Travis-API-Version: 3" \
            -H "Authorization: token ${KEY}" \
            -d "${body}" \
            "https://api.travis-ci.org/repo/${user}%2F${project}/requests"
    done
done
