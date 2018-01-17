### Development

Want to contribute? Great!

# How to install the Meilix-Generator using docker

## Deploying Locally

**Star** the repo and fork it and clone the forked one.

Open your favorite Terminal and run these commands.

Get started by creating docker image

```sh
docker build -t meilix-generator . 
```

Running the image, 
replace Travis Key with your token

```sh
docker run -p 8000:8000 \                      
--env email \
--env TRAVIS_TAG \
--env KEY='Travis Key' \
meilix-generator:latest
```

Note: see more [here](/docs/installation/my_token.md) about token and script

**Have an eye on the terminal to know about the process.**
