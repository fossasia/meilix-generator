# Deploy to Heroku

Want to contribute? Great!

To setup the meilix-generator on Heroku follow the following steps:


## Automatic Deploy

You can use the one click deployment

[![Deploy](https://www.herokucdn.com/deploy/button.svg)](https://heroku.com/deploy?template=https://github.com/fossasia/meilix-generator/tree/master)

**Note:** Make sure to generate your own tokens and API keys. Refer to [my_token.md](my_token.md) for details.


## Manual Deploy

You can setup your app on heroku manually

### Requirements

- [heroku toolbelt](https://devcenter.heroku.com/articles/heroku-cli) installed on your system
- _git_ installed on your system

### Clone repos and setup

Fork meilix-generator and meilix onto your account.

``` bash
$ git clone https://github.com/<your_username>/meilix-generator.git meilix-generator
```

Login into heroku

``` bash
$ heroku login
```

cd into the repository and create a heroku app
``` bash
$ cd meilix-generator

$ heroku create
Creating app... done, ⬢ your-heroku-app-name
https://your-heroku-app-name.herokuapp.com/ | https://git.heroku.com/your-heroku-app-name.git
```

**Note:** replace `<your-heroku-app-name>` with your heroku app name, and `<username>` with your GitHub username

Check if heroku's git url is added into the remote

``` bash
$ git remote -v
heroku	https://git.heroku.com/<your-heroku-app-name>.git (fetch)
heroku	https://git.heroku.com/<your-heroku-app-name>.git (push)
origin	https://github.com/<username>/meilix-generator.git (push)
origin	https://github.com/<username>/meilix-generaotr.git (push)
```

If it is not added automatically add the link to heroku's repository

``` bash
$ git remote add heroku https://git.heroku.com/<your-heroku-app-name>.git
```

Now push the onto Heroku
```sh
$ git push heroku master
```

Sometimes the server may take a while to start, the logs would say `State changed from starting to up` when the server is ready.

Open the URL of your server in your browser

```sh
$ heroku open
```

_Congrats you are done now!_. Your app should be available at https://your-heroku-app-name.herokuapp.com/

**Note:** Again, make sure to generate your own tokens and API keys. Refer to [my_token.md](my_token.md) for details.
