install:
	brew install python3.8

setup:
	pip3 install virtualenv
	virtualenv orderbook
	source orderbook/bin/activate
	pip3 install -r requirements.txt

run:
	python3 main.py
