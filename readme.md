# RPI timelapser

### CURRENTLY semi-FUNCTIONAL, I might've accidentally thrown half of it away :S

This script is supposed to run on an RPi with some sort of camera attached. 
It will first call a script that runs either untill stopped, or for a specified amount of time.

To use it run it via:

**To run indefinetly:**
```bash
	timelapse.py -p [period between images] -f [framerate]
```

**To run for duration with specified framrate**
```bash
	timelapse.py -f [framerate] -d [duration] -D [video duration]
```

**To run for duration with period**
```bash
	timelapse.py -p [period between images] -d [duration]
```
