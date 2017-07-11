url_wallpaper="https://meilix-generator.herokuapp.com/uploads/wallpaper" # url heroku wallpaper
wget $url_wallpaper -P usr/share/meilix/images/
sudo sed -i -e "s/xp_default_wallpaper.jpg/wallpaper/g" etc/xdg/pcmanfm/lubuntu/pcmanfm.conf
