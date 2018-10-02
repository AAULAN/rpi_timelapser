#!/usr/bin/env python3

from os import listdir
from os.path import isfile, join, splitext
import datetime
import subprocess
import math
from optparse import OptionParser, OptionGroup
import sys
from PIL import Image

opt_parser = OptionParser()

# Command line options

timing_options = OptionGroup(opt_parser, "Timing options")

timing_options.add_option(
	"-p", "--period",
	type="int", default=0,
	action="store", dest="period",
	help="Period between images in seconds")

timing_options.add_option(
	"-d", "--duration",
	type="int", default=0,
	action="store", dest="duration",
	help="Duration in seconds for the timelapser to run")

timing_options.add_option(
	"-r", "--framerate",
	type="int", default=10,
	action="store", dest="framerate",
	help="User specified framerate of the finished timelapse")

opt_parser.add_option_group(timing_options)

storage_options = OptionGroup(opt_parser, "Storage options")
storage_options.add_option(
	"-f", "--infolder",
	default="images",
	action="store", dest="in_folder",
	help="Folder to store images in")

storage_options.add_option(
	"-F", "--outfolder",
	default="output",
	action="store", dest="out_folder",
	help="Folder to store images in")

storage_options.add_option(
	"-t", "--type",
	default=".jpg",
	action="append", dest="allowed_types",
	help="Add allowed file types. Mostly intended for use without integrated image capture")
opt_parser.add_option_group(storage_options)

post_processing_options = OptionGroup(opt_parser, "Post Processing options")

post_processing_options.add_option(
	"-R", "--rotate",
	type="int", default=0,
	action="store", dest="rotate",
	help="Degrees to rotate image. Currently only 180 or 0 Deg is supported")

post_processing_options.add_option(
	"-c", "--crop",
	default=False,
	action="store_true", dest="crop",
	help="Crop image to supplied ratio requires ratio to be provided")
post_processing_options.add_option(
	"-a", "--ratio",
	type="float", default=0,
	action="append", dest="ratio",
	help="Desired output ratio, Ex: -a 16 -a 9 will be 16:9")
post_processing_options.add_option(
	"-s", "--scale", #TODO Ensure that this doesn't append inputs to the default 0
	default=0,
	action="append", dest="scale",
	help="Scale image to size. If only width is given it'll retain ratio. Ex: -s 1920 -s 1080")

opt_parser.add_option_group(post_processing_options)

(options, args) = opt_parser.parse_args()

# Option checker

# Calculate the missing timing variable
if options.framerate > 0:
	if options.duration > 0 and options.period == 0:
		options.period = options.duration / options.framerate
	elif options.period > 0 and options.duration == 0:
		options.duration = options.framerate * options.period
elif options.period and options.duration:
	options.framerate = options.duration / options.period
# If none of the above applies, there's an issue with the provided options
else:
	print("Incorrect timing options set")
	sys.exit(1)


# Ensure crop and ratio are both supplied if either are supplied
if bool(options.crop) != (options.ratio == 2):
	print("Crop and ratio have to be used together. ratio has to be 2 numbers")
	sys.exit(1)

# CONFIG START #

# The pattern passed to ffmpeg for images to look for. in this example it looks
# for images named img followed by 5 digits. fx 00001, then .jpg. 
# It's case sensitive
image_name_pattern = 'img%010d.jpg'

# Remote
remote = 'timelapser@rpiserv.local'
remote_folder = '/media/hdd/timelapser'

# Lazily using a timestamp to name the output. Should be pretty much entirely unique
video_name = 'Timelapse-{:%Y-%m-%d %H_%M_%S}'.format(datetime.datetime.now())

# CONFIG END #


# Get the last folder number on the remote

# TODO: USE NFS or SSHFS
# sudo sshfs -o allow_other,IdentityFile=~/.ssh/id_rsa timelapser@rpiserv.local:/media/hdd/timelapser /mnt/remote

command = [
	"ssh",
	remote,
	"ls " + remote_folder
]

p = subprocess.Popen(command, stdout=subprocess.PIPE)

(output, err) = p.communicate()
p.wait()

last = int(output.decode.strip('\n').split('_')[-1])

# Make new folder for new timelapse

folder = '/capture_' + str(last+1)

command = [
	"ssh",
	remote,
	"mkdir -p " + remote_folder + folder
]

p = subprocess.Popen(command, stdout=subprocess.PIPE)

(output, err) = p.communicate()
p.wait()

# Take the pictures



command = [
	'raspistill',
	'-t', '30000',
	'-tl', '2000',
	'-o', options.out_folder + '/' + image_name_pattern
]

def get_images(path, file_types):
	"This returns a list of all images of allowed type in the path"
	# print("Getting images from {} of type {}".format(path, ','.join(file_types)))
	print("Getting images from {}".format(path))

	# List all files and remove files that aren't images from the list
	images = [f for f in listdir(path) if isfile(join(path, f))]

	for item in images:
		file_name, ext = splitext(item)
		if ext.lower() not in [x.lower() for x in file_types]:
			images.remove(item)

	return images


# Rotate the images 180 degrees?
rotate = False

if options.rotate != 0:
	rotate = True

# Get a list of all images


images = get_images(options.in_folder, options.allowed_types)

img_count = len(images)

# Transformations
crop_argument = ''
scale_argument = ''
flip_argument = ''
if options.crop:

	if options.ratio.len() != 2:
		print('Invalid aspect ratio provided')
		sys.exit(2)

	# Get the dimensions of the first image.
	img = Image.open(options.in_folder + '/' + images[0])
	width, height = img.size
	img.close()

	cropped_height = math.floor(width * options.ratio[1] / options.ratio[0])
	crop_height_start = math.floor((height - cropped_height) / 2)

	crop_argument = 'crop={}:{}:0:{}'.format(width, cropped_height, crop_height_start)

if options.scale > 0:
	if options.scale.len() > 2:
		print('Invalid scale')
		sys.exit(3)
	elif options.scale.len() == 2:
		scale_argument = 'scale={}:{}'.format(options.scale[0], options.scale[1])
	else:
		scale_argument = 'scale={}:-1'.format(options.scale[0])

if rotate:
	flip_argument = 'hflip,vflip'

# construct transformation argument
first = True

transformation_argument = []

if options.crop:
	transformation_argument.append(crop_argument)

if options.scale:
	transformation_argument.append(scale_argument)

if rotate:
	transformation_argument.append(flip_argument)

# Transformations end

framerate = 0

if options.framerate == 0:
	framerate = math.floor(img_count / options.duration) + 1  # +1 to avoid a framerate of 0fps

# Construct subprocess list

command = [
	'ffmpeg',
	'-r', '{}'.format(framerate),
	'-f', 'image2',
	'-start_number', '0000000001.jpg',
	'-i', options.in_folder + '/' + image_name_pattern,
	'-codec:v', 'libx264']

if options.crop or options.scale != 0 or rotate != 0:
	command.append('-vf')
	command.append(transformation_argument)

command.append(options.out_folder + '/' + video_name + '.mp4')

print('Making timelapse with selected options now')
completed = subprocess.run(command)
print('Done')
