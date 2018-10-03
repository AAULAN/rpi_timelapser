#!/usr/bin/env python3

from os import listdir
from os.path import isfile, join, splitext
from optparse import OptionParser, OptionGroup
from time import sleep
import datetime
import subprocess
import math
import sys

try:
	from PIL import Image
except ImportError:
	sys.exit("You need Pillow!\ninstall it from https://pillow.readthedocs.io/en/3.3.x/installation.html#basic-installation")

try:
	import paramiko
except ImportError:
	sys.exit("You need Paramiko: pip3 install paramiko")

opt_parser = OptionParser()

# CONFIG START #

# The pattern passed to ffmpeg for images to look for. in this example it looks
# for images named img followed by 5 digits. fx 00001, then .jpg.
# It's case sensitive
image_name_pattern = 'img%010d.jpg'

# Remote
remote = {
	'host': '35.242.212.146',
	'port': 22,
	'user': 'timelapser',
	'key': '~/.ssh/id_rsa',
	'folder': '/home/timelapser/timelapses'
}

# Lazily using a timestamp to name the output. Should be pretty much entirely unique
video_name = 'Timelapse-{:%Y-%m-%d %H_%M_%S}'.format(datetime.datetime.now())
# CONFIG END

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
	type="float",
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
def check_options():
	if options.framerate == 0 or options.period == 0:
		sys.exit("Output framerate, and realtime period are both required")

	# Ensure crop and ratio are both supplied if either are supplied
	if bool(options.crop) != (len(options.ratio) == 2):
		sys.exit("Crop and ratio have to be used together. ratio has to be 2 numbers")


	if os.path.exists(options.in_folder) or os.path.exists(options.out_folder):
		sys.exit("Please make sure your input and output folders don't already exist")

def init():
	check_options()

	# Set up local image folder
	command = ['mkdir', '-p', options.in_folder]
	subprocess.run(command, stdout=subprocess.PIPE, check=True)

	# Get last output folder name on remote TODO: move this to paramiko SSH
	command = ["ssh", remote['user'] + '@' + remote['host'], "ls " + remote['folder']]
	p = subprocess.run(command, stdout=subprocess.PIPE, check=True)

	next_folder = 0
	if p.stdout is not None:
		next_folder = int(p.stdout.decode().strip('\n').split('_')[-1]) + 1


	print('Starting timelapse number: ' + str(next_folder))

	# Create new folder on remote TODO: move this to paramiko SSH
	command = ["ssh", remote['user'] + '@' + remote['host'], "mkdir -p " + remote['folder'] + 'capture_' + str(next_folder)]
	subprocess.run(command, check=True)

def put_images(images, local_path, remote_path, remove_files=False):
	sftp_client = create_sftp_client(remote['host'], remote['port'], remote['user'], None, remote['key'], 'RSA')

	for image in images:
		sftp_client.put(local_path + image, remote_path + image)

		if remove_files:
			os.remove(local_path + image)


def image_handling():
	command = [
		'raspistill',
		'-t', options.duration * 1000,
		'-tl', options.period * 1000,
		'-o', options.out_folder + '/' + image_name_pattern
	]
	p = subprocess.Popen(command)

	while p.poll() is None:
		imgs = get_images(options.in_folder, options.allowed_types)

		if len(imgs) >= 10:
			put_images(imgs)
		sleep(1)


# Found here: https://www.ivankrizsan.se/2016/04/28/implementing-a-sftp-client-using-python-and-paramiko/
def create_sftp_client(host, port, username, password, keyfilepath, keyfiletype):
	"""
	create_sftp_client(host, port, username, password, keyfilepath, keyfiletype) -> SFTPClient

	Creates a SFTP client connected to the supplied host on the supplied port authenticating as the user with
	supplied username and supplied password or with the private key in a file with the supplied path.
	If a private key is used for authentication, the type of the keyfile needs to be specified as DSA or RSA.
	:rtype: SFTPClient object.
	"""
	sftp = None
	key = None
	transport = None
	try:
		if keyfilepath is not None:
			# Get private key used to authenticate user.
			if keyfiletype == 'DSA':
				# The private key is a DSA type key.
				key = paramiko.DSSKey.from_private_key_file(keyfilepath)
			else:
				# The private key is a RSA type key.
				key = paramiko.RSAKey.from_private_key(keyfilepath)

		# Create Transport object using supplied method of authentication.
		transport = paramiko.Transport((host, port))
		transport.connect(None, username, password, key)

		sftp = paramiko.SFTPClient.from_transport(transport)

		return sftp
	except Exception as e:
		print('An error occurred creating SFTP client: %s: %s' % (e.__class__, e))
		if sftp is not None:
			sftp.close()
		if transport is not None:
			transport.close()
		pass


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


images = get_images(options.in_folder, options.allowed_types)

img_count = len(images)

# Transformations
crop_argument = ''
scale_argument = ''
flip_argument = ''
if options.crop:

	if options.ratio.len() != 2:
		sys.exit('Invalid aspect ratio provided')

	# Get the dimensions of the first image.
	img = Image.open(options.in_folder + '/' + images[0])
	width, height = img.size
	img.close()

	cropped_height = math.floor(width * options.ratio[1] / options.ratio[0])
	crop_height_start = math.floor((height - cropped_height) / 2)

	crop_argument = 'crop={}:{}:0:{}'.format(width, cropped_height, crop_height_start)

if options.scale > 0:
	if options.scale.len() > 2:
		sys.exit('Invalid scale')

	elif options.scale.len() == 2:
		scale_argument = 'scale={}:{}'.format(options.scale[0], options.scale[1])
	else:
		scale_argument = 'scale={}:-1'.format(options.scale[0])

if bool(options.rotate):
	flip_argument = 'hflip,vflip'

# construct transformation argument

transformation_argument = []

if options.crop:
	transformation_argument.append(crop_argument)

if options.scale:
	transformation_argument.append(scale_argument)

if bool(options.rotate):
	transformation_argument.append(flip_argument)

# Transformations end

# Construct subprocess list

command = [
	'ffmpeg',
	'-r', '{}'.format(options.framerate),
	'-f', 'image2',
	'-start_number', '0000000000.jpg',
	'-i', options.in_folder + '/' + image_name_pattern,
	'-codec:v', 'libx264']

if options.crop or options.scale != 0 or rotate != 0:
	command.append('-vf')
	command.append(transformation_argument)

command.append(options.out_folder + '/' + video_name + '.mp4')

print('Making timelapse with selected options now')
completed = subprocess.run(command)
print('Done')
