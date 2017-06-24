# Your Token
Till now if you are here, then you must have gone through the code.
### [travis_tokens](/travis_tokens)
It contain 3 words as :
`username repository branch`
This is the user whose branch of that repository is going to be trigger.
We are using [fossasia/meilix](https://github.com/fossasia/meilix) repository to trigger its build.

**Before undergoing any development process you must fork [fossasia/meilix](https://github.com/fossasia/meilix) repository and change the username so that the release will be done in your repository**.
You can fork [this](https://github.com/fossasia/meilix) and start to put **your username** so that the fossasia/meilix repo will not get flooded with unnecessary builds. And your can easily play with configuration without disturbing the original repo.

### [script.sh](/script.sh)
This contains an line as
`echo "https://github.com/fossasia/meilix/releases/download/${TRAVIS_TAG}/meilix-zesty-`date +%Y%m%d`-i386.iso"`

change it to:
`echo "https://github.com/user_name/meilix/releases/download/${TRAVIS_TAG}/meilix-zesty-`date +%Y%m%d`-i386.iso"`

Where the *user_name* is your github profile username where you have forked the **meilix** repo.

Since in the above step you changed the repository which is going to be used for triggering the build, so the iso will also be released in the that repository only.

### Generate your own token
To get the access to recognise the Heroku that you are the one who is going to trigger the build of meilix in Travis, we need to provide config variable in Heroku generated through Travis.

Install Travis and run the following to login

```sh
travis login --org
```

Now cd into the forked repo of meilix and generate token

```sh

cd meilix-generator
travis token --org
```

###### Paste this token in config variable present in setting of the Heroku app and add KEY as `KEY` and VALUE as the `access token`.
**Refer [here](https://docs.google.com/document/d/1agoZ3pSKjUfwSAJ3Yu0m-P08M4ERPIjiwSOSU3bubG0/edit?usp=sharing) for more info about the token generation**

> Now you are ready to go. Deploy your app.
