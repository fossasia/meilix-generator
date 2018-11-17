# Token configuration

Travis builds require special credentials to be triggered over Travis API.

**You need to have a clone of meilix-generator and meilix, so that you can control them and deploy your own builds. Enable Travis builds on your meilix repo.**


## [travis_tokens](/travis_tokens)

This file specifies on which repo to trigger build on and which branch to use. It looks like

```
<username> <repo_name> <branch>
```

> **Note:** For your own development be sure to change these tokens.


## [script.sh](/script.sh)

Change release link from
```
echo "https://github.com/fossasia/meilix/releases/download/${TRAVIS_TAG}/meilix-zesty-`date +%Y%m%d`-i386.iso"
```
to
```
echo "https://github.com/<username>/meilix/releases/download/${TRAVIS_TAG}/meilix-zesty-`date +%Y%m%d`-i386.iso"
```

**<username** is your user/organization name where you have cloned meilix to.

Your iso will be released to your fork of meilix.


## Generate travis keys

To trigger builds on travis you need Travis API key. In `script.sh` we use the API key to trigger the build.

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

Now use the access token to specify an environment variable `KEY` on your development instance(say Heroku) where meilix-generator is hosted.
`script.sh` uses this `KEY` to trigger a build on Travis.

To publish releases on GitHub you need to setup your release key

``` bash
# in meilix repo
$ travis encrypt <token> --add
```

> **Note:** This will replace the existing GH releases key to your own. Remember you will be pushing this encrypted token on to GitHub.

If you have any problems with token generation don't bother to rant on [https://gitter.im/fossasia/meilix](https://gitter.im/fossasia/meilix)

