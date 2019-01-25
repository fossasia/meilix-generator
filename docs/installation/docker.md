### Development

Want to contribute? Great!

# How to install the Meilix-Generator using docker

## Deploying Locally

**Step 0**  Star the repo and fork it and clone the forked one.
```
git clone https://github.com/<your_username>/meilix-generator.git
```

**Step 1** Open your favorite Terminal and run these commands.

Firstly, to create the docker image

```sh
docker build -t meilix-generator .
```

**Step 2** Now run the docker image. Replace Travis Key with your token.

*Note: see more [here](/docs/installation/my_token.md) about token and script*

```sh
docker run -p 8000:8000 \                      
--env email \
--env TRAVIS_TAG \
--env KEY='Travis Key' \
meilix-generator:latest
```
**Step 3** Navigate to [http://localhost:8000/](http://localhost:8000/) to see the docker image up and running.

**Keep an eye on the terminal to know about the process.**
