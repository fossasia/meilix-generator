### Development

Want to contribute? Great!

To setup the meilix-generator on Heroku follow the following steps:


# Manual Deploy

You can setup your app on heroku manually:

# Requirements:
- **heroku toolbelt** installed on your system
For more info on heroku toolbelt: [here](https://devcenter.heroku.com/articles/heroku-cli)
- **git** installed on your system
# Installation with Heroku

Open your favorite Terminal and run these commands.

first **start** the repo, fork and clone it:
```sh
$ git clone https://github.com/yourusername/meilix-generator.git
```

login into heroku toolbelt:
```sh
$ heroku login
```

cd into the repository and create a heroku app
```sh
$ heroku create
Creating app... done, ⬢ your-heroku-app-name
https://your-heroku-app-name.herokuapp.com/ | https://git.heroku.com/your-heroku-app-name.git
```
**Note:** replace 'your-heroku-app-name' with your heroku app name

check if heroku's git url is added into the remote
```sh
$ git remote -v
heroku	https://git.heroku.com/your-heroku-app-name.git (fetch)
heroku	https://git.heroku.com/your-heroku-app-name.git (push)
origin	https://github.com/yourusername/meilix-generator.git (push)
origin	https://github.com/yourusername/meilix-generaotr.git (push)
```
if it is not added automatically add the link to heroku's repository by typing following command in terminal
```sh
$ git remote add heroku https://git.heroku.com/your-heroku-app-name.git
```

now push the code
```sh
$ git push heroku master
```

sometimes the server may take a while to start, the logs would say `State changed from starting to up` when the server is ready.

open the URL of your server in your browser
```sh
$ heroku open
```

> *Congrats you are done now!*

Note: see more [here](/docs/installation/my_token.md) about token and script before attempting the above steps.

- Your app should be available at : https://your-heroku-app-name.herokuapp.com/
