#!/usr/bin/env bash
desktop_path=$(grep "XDG_DESKTOP_DIR" $HOME/.config/user-dirs.dirs | sed 's/XDG_DESKTOP_DIR=//')
eval cd "$desktop_path"

if [[ $1 =~ "tar.gz" ]]; then
	tar -xzf $1 -C .
else
	sudo apt install unzip
	unzip $1 -d .
fi
