#!/usr/bin/python3

# pylint: disable-msg=C0103

from os import listdir
from os.path import isfile, join, splitext
import datetime
import subprocess
import math
from optparse import OptionParser
from PIL import Image


opt_parser = OptionParser()

# Command line options

opt_parser.add_option("-p", "--period",
                      type="int", default=0,
                      action="store", dest="period",
                      help="Period between images in seconds")

opt_parser.add_option("-d", "--duration",
                      type="int", default=0,
                      action="store", dest="duration",
                      help="Duration in seconds for the timelapser to run")

opt_parser.add_option("-r", "--framerate",
                      type="int", default=10,
                      action="store", dest="framerate",
                      help="User specified framerate of the finished timelapse")

opt_parser.add_option("-f", "--infolder",
                      default="images",
                      action="store", dest="in_folder",
                      help="Folder to store images in")

opt_parser.add_option("-F", "--outfolder",
                      default="output",
                      action="store", dest="out_folder",
                      help="Folder to store images in")

opt_parser.add_option("-r", "--rotate",
                      type="int", default= 0,
                      action="store", dest="rotate",
                      help="Degrees to rotate image. Currently only 180 or 0 Deg is supported")

opt_parser.add_option("-t", "--type",
                      default=".png",
                      action="append", dest="allowed_types",
                      help="Add allowed file type")


(options, args) = opt_parser.parse_args()

## CONFIG START

# Filetypes looked for (This is used for converting duration to framrate)
allowedFileExtensions = ['.png', '.jpg']

# The pattern passed to ffmpeg for images to look for. in this example it looks
# for images named img followed by 5 digits. fx 00001, then .jpg. 
# It's case sensitive
image_name_pattern = 'img%05d.jpg'

# Rotate the images 180 degrees?
rotate = False

# Crop the image?
crop = True
crop_ratio = [16, 9] # Crop to a 16/9 format

# Scale the image?
scale = False
scale_width = 1920

#Lazily using a timestamp to name the output. Should be pretty much entirely unique
video_name = 'Timelapse-{:%Y-%m-%d %H_%M_%S}'.format(datetime.datetime.now())


## CONFIG END


# Processing configs here

# Get a list of all images
images = [f for f in listdir(image_path) if isfile(join(image_path, f))]
for item in images:
    allowed = False
    fn, ext = splitext(item)
    for allowedExt in allowedFileExtensions:
        if ext.lower() == allowedExt.lower():
            allowed = True
    if not allowed:
        images.remove(item)

img_count = len(images)

# Transformations
if crop:
    img = Image.open(image_path + '/' + images[0])
    width, height = img.size
    img.close()

    cropped_height = math.floor(width * crop_ratio[1]/crop_ratio[0])
    crop_height_start = math.floor((height - cropped_height)/2)

    crop_argument = 'crop={}:{}:0:{}'.format(width,cropped_height,crop_height_start)

if scale:
    scale_argument = 'scale={}:-1'.format(scale_width)

if rotate:
    flip_argument = 'hflip,vflip'

# construct transformation argument
first = True
if crop:
    first = False
    transformation_argument = crop_argument

if scale:
    if not first:
        transformation_argument += ','

    first = False
    transformation_argument += scale_argument

if rotate:
    if not first:
        transformation_argument += ','

    first = False
    transformation_argument += flip_argument

# Transformations end

if framerate == 0:
    framerate = math.floor(img_count / desired_video_duration)+1 # +1 to avoid a framerate of 0fps

# Construct subprocess list

command = ['ffmpeg', '-r', '{}'.format(framerate), '-f', 'image2', '-start_number', start_number, '-i', image_path + '/' + image_name_pattern, '-codec:v', 'libx264'] 

if crop or scale or rotate:
    command.append('-vf')
    command.append(transformation_argument)

command.append(video_name + '.mp4')

print('Making timelapse with selected options now')
completed = subprocess.run(command, )
print('Done')