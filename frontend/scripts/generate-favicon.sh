#!/bin/bash

# Generate favicon.ico from SVG using ImageMagick
# Requires: sudo apt-get install imagemagick

echo "Generating favicon.ico from favicon.svg..."

# Create multiple sizes for ICO file
convert -background transparent ../public/favicon.svg -resize 16x16 favicon-16.png
convert -background transparent ../public/favicon.svg -resize 32x32 favicon-32.png
convert -background transparent ../public/favicon.svg -resize 48x48 favicon-48.png
convert -background transparent ../public/favicon.svg -resize 64x64 favicon-64.png
convert -background transparent ../public/favicon.svg -resize 128x128 favicon-128.png
convert -background transparent ../public/favicon.svg -resize 256x256 favicon-256.png

# Combine into ICO file
convert favicon-16.png favicon-32.png favicon-48.png favicon-64.png favicon-128.png favicon-256.png ../public/favicon.ico

# Clean up temporary files
rm favicon-*.png

echo "favicon.ico generated successfully!"

# Also generate other web app icons
echo "Generating additional web app icons..."

# Apple Touch Icon
convert -background transparent ../public/favicon.svg -resize 180x180 ../public/apple-touch-icon.png

# Android Chrome icons
convert -background transparent ../public/favicon.svg -resize 192x192 ../public/android-chrome-192x192.png
convert -background transparent ../public/favicon.svg -resize 512x512 ../public/android-chrome-512x512.png

# Favicon for modern browsers
convert -background transparent ../public/favicon.svg -resize 32x32 ../public/favicon-32x32.png
convert -background transparent ../public/favicon.svg -resize 16x16 ../public/favicon-16x16.png

echo "All icons generated successfully!"