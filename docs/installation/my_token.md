# Token configuration

Travis builds require special credentials to be triggered over Travis API.

**You need to have a clone of meilix-generator and meilix, so that you can control them and deploy your own builds. Enable Travis builds on your meilix repo.**

## Generate travis keys

To trigger builds on travis you need Travis API key. In , `build.py` we use the API key to trigger the build.

To generate travis token [install it](https://github.com/travis-ci/travis.rb#installation) and run

``` bash
$ travis login --org
```

Now cd into the forked repo of meilix and generate token

``` bash
# change into meilix repo
$ cd meilix

# generate a token for this specific repo
$ travis token
```

## Managing heroku config vars using heroku cli

We will use the heroku cli to set an environment variable `KEY` for your development instance (Heroku) where your webapp is hosted.  
`build.py` uses this `KEY` to trigger a build on Travis.

``` bash
# Setting a config var KEY
$ heroku config:set KEY=<travis_token>

# Viewing current config values
$ heroku config
```

To publish releases on GitHub you need to setup your release key

``` bash
# in meilix repo
$ travis encrypt <token> --add
```

> **Note:** This will replace the existing GH releases key to your own. Remember you will be pushing this encrypted token on to GitHub.

If you have any problems with token generation don't bother to rant on [https://gitter.im/fossasia/meilix](https://gitter.im/fossasia/meilix)

