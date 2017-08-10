#!/usr/bin/env bash
echo "$Wallpaper" | base64 --decode > wallpaper
for f in wallpaper; do
	type=$( file "$f" | grep -oP 'w+(?)= image data' )
	case $type in
		PNG) newext=png ;;
        JPEG) newext=jpg ;; 
        *)    echo "??? what is this: $f"; continue ;; 
    esac
    mv "$f" "${f%.*}.$newexng ;; 
            JPEG) newext=jpg ;; 
            *)    echo "??? what is this: $f"; continue ;; 
        esac
        mv "$f" "${f%.*}.$newext"
        done

ls
