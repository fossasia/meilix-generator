![Meilix Generator](https://preview.ibb.co/hjxP3Q/m_g.jpg)


# Meilix Generator

[![N|Solid](https://image.ibb.co/fZ5m05/powered_by_flask_s.png)](http://flask.pocoo.org/)

Meilix-Generator is a webapp which generates iso using [meilix](https://github.com/fossasia/meilix) script.

  - [fossasia/meilix](https://github.com/fossasia/meilix) consists the script of a Linux Operating System based on Lubuntu. It uses Travis to build that script to result in a release of an iso file.
  - Now we thought an idea of building an autonomous system to start this build and get the release and in the meanwhile also make some required changes to the script to get it into the OS. We came up with an idea of a webapp which ask user it’s email id and tag of the build and till now a picture from the user which will be set as a wallpaper. Means user can able to config its distro according to its need through the graphical interface without a single line to code from the user end.
  - Through the webapp, a build button is taken as an input to go to a build page which triggers the Travis with the same user configuration to build the iso and deploy it on Github page. The user gets the link to the build on the next page only.
  - Thanks to [Travis API](https://blog.travis-ci.com/2017-04-06-api-v3-is-here) without which our idea is impossible to implement. We used a [shell script](/docs/installation/my_token.md) to outframe our idea. The script takes the input of the user’s, repository, and branch to decide to where the trigger to take place.

[![Travis branch](https://img.shields.io/travis/fossasia/meilix-generator/master.svg?style=flat-square)](https://travis-ci.org/fossasia/meilix-generator) [![Gemnasium](https://img.shields.io/gemnasium/fossasia/meilix-generator.svg?style=flat-square)](https://gemnasium.com/github.com/fossasia/meilix-generator) [![Heroku](https://heroku-badge.herokuapp.com/?app=meilix-generator)](https://meilix-generator.herokuapp.com/) [![Gitter](https://badges.gitter.im/Join%20Chat.svg)](https://gitter.im/fossasia/meilix?utm_source=badge&utm_medium=badge&utm_campaign=pr-badge&utm_content=badge)

## Communication

Please join our mailing list to discuss questions regarding the project: https://groups.google.com/forum/#!forum/meilix

Our chat channel is on Gitter here: [gitter.im/fossasia/open-event-orga-server](https://gitter.im/fossasia/meilix)

# New Features!

  - User can give their own configuration
  - Travis will build for them
  - Github will release the iso
  - User can upload wallpaper which will be set as desktop background


You can
  - Get the iso within 20 minutes of starting of the build

Meilix Generator can generate iso for you based upon your configuration and need.

> The main aim for the project is to help a user/organisation to make its own linux distro which he/she can use, share and distribute.

### Technologies Used

Meilix-Generator uses a number of open source projects to work properly:

* [Flask](http://flask.pocoo.org/) - Microframework powered by python
* [Bootstrap](http://getbootstrap.com/) - Responsive frontend framework for webapp
* [Shell](https://en.wikipedia.org/wiki/Unix_shell) - Script used for triggering Travis using [Travis API](https://docs.travis-ci.com/user/triggering-builds/)
* [Heroku](https://www.heroku.com/) - Webapp deployed here
* [Travis](travis-ci.org) - Continuous Integration which build the iso
* [Github Release](https://help.github.com/articles/creating-releases/) - Deploying the iso here

#### Components and its working

1. Webapp

The source of the webapp frontend can be found [here](/templates). It consists of:

- [index.html](/templates/index.html) - The webform page
- [404.html](/templates/404.html) - The non-found page

2. Generator

The generator runs on flask framework, using the main [app script](/app.py)

3. [Scripts](/docs/installation/my_token.md)

- [script.sh](/script.sh) - Use the Travis API to trigger the build
- [travis_tokens](/travis_tokens) - Sends the user, repo and branch required for triggering to [script.sh](/script.sh).

##### Working
Webapp ask user for their email-id and event name and a wallpaper which will further be the default wallpaper of the distro. The given event name is used as a tag name of the release.
Heroku sends these data to Travis to trigger the build. After successful build Travis deployed the iso in the Github Release of the repository whose information is provided in [travis_tokens](/travis_tokens).

### Installation

**Please go through all the docs before starting the development process**

The meilix-generator can be easily deployed on a variety of platform. Detailed platform specific installation instructions have been provided below:

1. [Local Installation](/docs/installation/local.md)
2. [Deployment on Heroku](/docs/installation/heroku.md)

## Contributions, Bug Reports, Feature Requests

This is an Open Source project and we would be happy to see contributors who report bugs and file feature requests submitting pull requests as well. Please report issues here https://github.com/fossasia/meilix-generator/issues

## Issue and Branch Policy

Before making a pull request, please file an issue. So, other developers have the chance to give feedback or discuss details. Match every pull request with an issue please and add the issue number in description e.g. like "Fixes #123".

We have the following branches
* **master**
    All development goes on in the master branch. If you're making a contribution, you are supposed to make a pull request to master. PRs to the branch must pass a build check and a unit-test check on Travis.

## Contributions Best Practices

**Commits**
* Follow the template of while creating issues and before making a PR.
* Write clear meaningful git commit messages (Do read http://chris.beams.io/posts/git-commit/)
* Make sure your PR's description contains GitHub's special keyword references that automatically close the related issue when the PR is merged. (More info at https://github.com/blog/1506-closing-issues-via-pull-requests )
* When you make very very minor changes to a PR of yours (like for example fixing a failing travis build or some small style corrections or minor changes requested by reviewers) make sure you squash your commits afterwards so that you don't have an absurd number of commits for a very small fix. (Learn how to squash at https://davidwalsh.name/squash-commits-git )
* When you're submitting a PR for a UI-related issue, it would be really awesome if you add a screenshot of your change or a link to a deployment where it can be tested out along with your PR. It makes it very easy for the reviewers and you'll also get reviews quicker.
* Collective Code Construction Contract (https://rfc.zeromq.org/spec:42/C4/)

**Feature Requests and Bug Reports**
* When you file a feature request or when you are submitting a bug report to the [issue tracker](https://github.com/fossasia/meilix-generator/issues), make sure you add steps to reproduce it. Especially if that bug is some weird/rare one.

**Join the development**
* Before you join development, please set up the system on your local machine and go through the application completely. Press on any link/button you can find and see where it leads to. Explore. (Don't worry ... Nothing will happen to the app or to you due to the exploring :wink: Only thing that will happen is, you'll be more familiar with what is where and might even get some cool ideas on how to improve various aspects of the app.)
* If you would like to work on an issue, drop in a comment at the issue. If it is already assigned to someone, but there is no sign of any work being done, please free to drop in a comment so that the issue can be assigned to you if the previous assignee has dropped it entirely.

**Write-up containing project buildup**
* These documents will help you to know more about the backbone of the project: [Flask](https://docs.google.com/document/d/1TWsz0aP0vLwXwcTX1VC58lEYy5dM6xvxnAABEtzyUZY/edit?usp=sharing) and [Heroku Travis Intergration](https://docs.google.com/document/d/19xBAbjH04e_KlWwzGiDCDVAs4bLv-d-lcjKyr6bTRWE/edit?usp=sharing)


## License

This project is currently licensed under GNU Lesser General Public License v3.0 (LGPL-3.0). A copy of LICENSE.md should be present along with the source code. To obtain the software under a different license, please contact FOSSASIA.

*If you like the project, don't forget to **star** it.*
