#!/usr/bin/env python3

from os import listdir, remove, symlink
import errno
from os.path import isfile, join, splitext
from optparse import OptionParser, OptionGroup
from time import sleep, time
import datetime
import subprocess
import math
import sys
import tempfile

from shutil import copyfile

try:
	from PIL import Image
except ImportError:
	sys.exit(
		"You need Pillow!\nInstall it from https://pillow.readthedocs.io/en/3.3.x/installation.html#basic-installation")

try:
	import paramiko
except ImportError:
	sys.exit("You need Paramiko!\nInstall it with: pip3 install paramiko")

opt_parser = OptionParser()

# CONFIG START #

# The pattern passed to ffmpeg for images to look for. in this example it looks
# for images named img followed by 5 digits. fx 00001, then .jpg.
# It's case sensitive
image_name_pattern = 'img%05d.jpg'

# Remote
remote_info = {
	'host': '35.242.212.146',
	'port': 22,
	'user': 'timelapser',
	'key': '/home/timelapser/.ssh/id_rsa',
	'folder': '/home/timelapser/timelapses'
}


# CONFIG END


def create_command_line_options():
	# Command line options
	timing_options = OptionGroup(opt_parser, "Timing options")
	timing_options.add_option(
		"-p", "--period",
		type="int",
		action="store", dest="period",
		help="Period between images in seconds")

	timing_options.add_option(
		"-d", "--duration",
		type="int",
		action="store", dest="duration",
		help="Duration in seconds for the timelapser to run")

	timing_options.add_option(
		"-D", "--videoduration",
		type="int",
		action="store", dest="vid_duration",
		help="Duration in seconds for the final video")

	timing_options.add_option(
		"-f", "--framerate",
		type="int",
		action="store", dest="framerate",
		help="User specified framerate of the finished timelapse")

	opt_parser.add_option_group(timing_options)

	storage_options = OptionGroup(opt_parser, "Format options")

	storage_options.add_option(
		"-l", "--local",
		action="store", dest="local_storage",
		help="Supply a local path to run this independent of a remote server. No FFMPEG will be run. Ex: -l /home/[user]/timelapses"
	)

	storage_options.add_option(
		"-t", "--type",
		default=".jpg",
		action="append", dest="allowed_types",
		help="Add allowed file types. Mostly intended for use without integrated image capture")
	opt_parser.add_option_group(storage_options)

	post_processing_options = OptionGroup(opt_parser, "Post Processing options")

	post_processing_options.add_option(
		"-F", "--onlyffmpeg",
		action="store", dest="ffmpeg_only",
		help="Specify input folder with images, to run ffmpeg on standalone. Ex: -F /home/[user]/timelapses/timelapse1"
	)

	post_processing_options.add_option(
		"-r", "--rotate",
		type="int", default=0,
		action="store", dest="rotate",
		help="Degrees to rotate image. Currently only 180 or 0 Deg is supported")
	post_processing_options.add_option(
		"-c", "--crop",
		type="float",
		action="append", dest="crop",
		help="Crop image to supplied ratio ex: -c 16 -c 9")
	post_processing_options.add_option(
		"-s", "--scale",  # TODO Ensure that this doesn't append inputs to the default 0
		default=0,
		action="append", dest="scale",
		help="Scale image to size. If only width is given it'll retain ratio. Ex: -s 1920 -s 1080")

	opt_parser.add_option_group(post_processing_options)

	(options, args) = opt_parser.parse_args()

	return options


# Found here: https://www.ivankrizsan.se/2016/04/28/implementing-a-sftp-client-using-python-and-paramiko/
def create_sftp_client(host, port, username, password=None, keyfilepath=None, keyfiletype=None, skip_sftp=False):
	"""
	create_sftp_client(host, port, username, password, keyfilepath, keyfiletype) -> SFTPClient

	Creates a SFTP client connected to the supplied host on the supplied port authenticating as the user with
	supplied username and supplied password or with the private key in a file with the supplied path.
	If a private key is used for authentication, the type of the keyfile needs to be specified as DSA or RSA.
	:rtype: SFTPClient object.
	"""
	ssh = None
	sftp = None
	key = None
	try:
		if keyfilepath is not None:
			key_file = open(keyfilepath, 'r')
			# Get private key used to authenticate user.
			if keyfiletype == 'DSA':
				# The private key is a DSA type key.
				key = paramiko.DSSKey.from_private_key_file(key_file)
			else:
				# The private key is a RSA type key.
				key = paramiko.RSAKey.from_private_key(key_file)

			key_file.close()

		# Connect SSH client accepting all host keys.
		ssh = paramiko.SSHClient()
		ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
		ssh.connect(host, port, username, password, key)

		if skip_sftp:
			return ssh

		# Using the SSH client, create a SFTP client.
		sftp = ssh.open_sftp()
		# Keep a reference to the SSH client in the SFTP client as to prevent the former from
		# being garbage collected and the connection from being closed.
		sftp.sshclient = ssh

		return sftp
	except Exception as e:
		print('An error occurred creating SFTP client: %s: %s' % (e.__class__, e))
		if sftp is not None:
			sftp.close()
		if ssh is not None:
			ssh.close()
		pass


# Option checker
def check_options():
	opt = create_command_line_options()

	# Timing option checks
	timing_options_set = 0

	if bool(opt.framerate):
		timing_options_set += 1

	if bool(opt.period):
		timing_options_set += 1

	if bool(opt.duration):
		timing_options_set += 1

	if bool(opt.vid_duration):
		timing_options_set += 1

	if timing_options_set > 3:
		sys.exit("Too many timing options provided")

	if timing_options_set <= 3:
		if timing_options_set == 2:
			if bool(opt.period) and (bool(opt.framerate) or bool(opt.vid_duration)):
				pass
			else:
				sys.exit("For indefinite running, you have to supply period and (framerate or video duration)")

		elif timing_options_set == 3:
			if opt.framerate is None:
				opt.framerate = opt.duration / (opt.period * opt.vid_duration)

			elif opt.period is None:
				opt.period = opt.duration / (opt.framerate * opt.vid_duration)

			elif opt.duration is None:
				opt.duration = opt.period * opt.framerate * opt.vid_duration

			elif opt.vid_duration is None:
				opt.vid_duration = opt.duration / (opt.framerate * opt.period)

			else:
				sys.exit("what happened in the option checker?")

		else:
			sys.exit("Too few timing parameters given")

	if bool(opt.local_storage):
		return opt

	if bool(opt.ffmpeg_only):
		return opt

	# Ensure crop and ratio are both supplied if either are supplied
	if len(opt.crop) != 2:
		sys.exit("Crop requires two numbers")

	return opt


def init(remote):
	# Set up local image folder
	temp_dir = tempfile.TemporaryDirectory()

	# Get last output folder name on remote
	sftp_client = create_sftp_client(remote['host'], remote['port'], remote['user'], None, remote['key'], 'RSA')
	ls_list = sftp_client.listdir(remote['folder'])

	next_folder = 0
	if bool(ls_list):
		for folder in ls_list:
			x = int(folder.split('_')[-1])
			if x > next_folder:
				next_folder = x
		next_folder += 1

	print('Starting timelapse number: ' + str(next_folder))

	# Create new folder on remote
	sftp_client.mkdir(remote['folder'] + '/capture_' + str(next_folder))
	sftp_client.close()

	remote_dir = 'capture_' + str(next_folder)

	return temp_dir, remote_dir


def put_images(images, local_path, remote_dir, remote, remove_files=False):
	sftp_client = create_sftp_client(remote['host'], remote['port'], remote['user'], None, remote['key'], 'RSA')

	print(images)

	for image in images:
		print("Moving {}".format(local_path + '/' + image))
		sftp_client.put(local_path + '/' + image, remote['folder'] + '/' + remote_dir + '/' + image)

		if remove_files:
			remove(local_path + '/' + image)

	sftp_client.close()


def put_image(local_path, remote_path, remote, remove_files=False):
	sftp_client = create_sftp_client(remote['host'], remote['port'], remote['user'], None, remote['key'], 'RSA')

	sftp_client.put(local_path, remote_path)

	if remove_files:
		remove(local_path)

	sftp_client.close()


def symlink_force(target, link_name):

	try:
		symlink(target, link_name)
	except OSError as e:
		if e.errno == errno.EEXIST:
			remove(link_name)
			symlink(target, link_name)
		else:
			raise e


def image_handling(duration, period, local_path, remote_dir, name_pattern, allowed_types, remote, rotate=False):
	base_command = ['raspistill']

	if rotate:
		base_command += ['-hf', '-vf']

	base_command += ['-o', local_path + '/']

	imgs = get_images(local_path, allowed_types)

	last_image = 0
	last_image_time = 0
	start = time()
	while time() - start < duration:
		if time() - last_image_time >= period:
			command = base_command[:]
			command[-1] += name_pattern % (last_image + 1,)
			last_image += 1
			subprocess.run(command)

			symlink_force(command[-1], local_path + '/' + 'latest.jpg')

			if remote_dir is not None:
				put_image(command[-1], remote['folder'] + '/' + remote_dir + '/' + command[-1].split('/')[-1], remote,
						  True)

		else:
			sleep(1)  # Avoid a busy loop

	# Timelapse done, move the rest of the images
	if remote_dir is not None:
		imgs = get_images(local_path, allowed_types)
		put_images(imgs, local_path, remote['folder'], remote, True)


def get_images(path, file_types, local=True, remote=None):
	"""This returns a list of all images of allowed type in the path"""
	# print("Getting images from {} of type {}".format(path, ','.join(file_types)))
	print("Getting images from {}".format(path))

	images = None

	if local:
		images = [f for f in listdir(path) if isfile(join(path, f))]

	elif remote is not None:
		sftp_client = create_sftp_client(remote['host'], remote['port'], remote['user'], None, remote['key'], 'RSA')
		images = sftp_client.listdir(remote['folder'])
		sftp_client.close()

	for item in images:
		file_name, ext = splitext(item)
		if ext.lower() not in [x.lower() for x in file_types]:
			images.remove(item)

	return images


def get_image_size(remote, allowed_type):
	images = get_images(None, allowed_type, False, remote)

	with tempfile.TemporaryDirectory() as temp:
		sftp_client = create_sftp_client(remote['host'], remote['port'], remote['user'], None, remote['key'], 'RSA')
		sftp_client.get(temp.name + '/' + images[0], remote['folder'] + '/' + images[0])
		sftp_client.close()

		img = Image.open(temp.name + '/' + images[0])
		width, height = img.size
		img.close()

	return [width, height]


def get_transformation(size, crop=None, scale=None, rotate=0):
	"""Constructs a list of transform operations for ffmpeg"""

	tf_arg = []
	crop_argument = ''
	scale_argument = ''
	flip_argument = ''

	if bool(crop):
		cropped_height = math.floor(size[0] * crop[1] / crop[0])
		crop_height_start = math.floor((size[1] - cropped_height) / 2)

		crop_argument = 'crop={}:{}:0:{}'.format(size[0], cropped_height, crop_height_start)

	if bool(scale):
		if len(scale) > 2:
			sys.exit('Invalid scale')

		elif len(scale) == 2:
			scale_argument = 'scale={}:{}'.format(scale[0], scale[1])
		else:
			scale_argument = 'scale={}:-1'.format(scale[0])

	if bool(rotate):
		pass  # flip_argument = 'hflip,vflip'

	# construct transformation argument

	if bool(crop):
		tf_arg.append(crop_argument)

	if scale:
		tf_arg.append(scale_argument)

	if bool(rotate):
		pass  # tf_arg.append(flip_argument)

	return ' '.join(map(str, tf_arg))


def get_ffmpeg_command(framerate, remote_folder, name_pattern, transform):
	"""This command generates the ffmpeg command string to execute on the remote host"""
	command = [
		'ffmpeg',
		'-r', '{}'.format(framerate),
		'-f', 'image2',
		'-start_number', '0000000001',
		'-i', '{}/{}'.format(remote_folder, name_pattern),
		'-codec:v', 'libx264']

	if bool(transform):
		command.append('-vf')
		command.append(transform)

	# Lazily using a timestamp to name the output. Should be pretty much entirely unique
	video_name = 'Timelapse-{:%Y-%m-%d_%H-%M-%S}'.format(datetime.datetime.now())

	command.append(remote_folder + '/' + video_name + '.mp4')

	return command


def make_video(ffmpeg_command, remote):
	command = 'nohup '
	command += ' '.join(map(str, ffmpeg_command))
	command += ' &'

	ssh_client = create_sftp_client(remote['host'], remote['port'], remote['user'], None, remote['key'], 'RSA', True)
	ssh_client.exec_command(command)
	ssh_client.close()


if __name__ == "__main__":
	print("Checking options")
	options = check_options()

	local_dir, remote_dir = None, None
	if bool(options.local_storage):
		local_dir = options.local_storage
	elif not bool(options.ffmpeg_only):
		local_dir, remote_dir = init(remote_info)
		local_dir = local_dir.name
		print("Set up temporary local folder {}".format(local_dir))

	print("Starting timelapse with settings: {}s period, ".format(options.period))

	if not bool(options.ffmpeg_only):
		image_handling(options.duration, options.period, local_dir, remote_dir, image_name_pattern,
					   options.allowed_types, remote_info, bool(options.rotate))

	if remote_dir is not None or bool(options.ffmpeg_only):
		size = get_image_size(remote_info, options.allowed_types)
		transform = get_transformation(size, options.crop, options.scale, options.rotate)
		ffmpeg_command = get_ffmpeg_command(options.framrate, remote_info['folder'], 'img%010d.jpg', transform)

	print('Making timelapse with selected options now')
# make_video(ffmpeg_command, remote_info)
