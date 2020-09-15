install:
	brew install python3.8

setup:
	pip3 install virtualenv
	virtualenv coin routes
	source coinroutes/bin/activate
	pip3 install -r requirements.txt

run:
	python3 coinroutes_challenge.py
