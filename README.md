## BTC OrderBOok
#### This script gets a selection of orders from three exchanges (Coinbase, Gemini, and Kraken) given a quantity. It returns a selection of orders, the total price and total coins of said selection.

### Getting Started

##### This script requires a python version of 3.8 or higher. Any earlier version will have breaking changes. A make file is provided to help you get started.
* ```make install``` will install `python3.8` on your system
* ```make setup``` will create a virtual `python` environment and install all dependencies to run the script
* ```make run``` will run the script with default quantities
##### To run the script without `make run` you can type `python3 coinroutes_challenge.py`. You can add optional flags as well. 

##### This script offers three flags 
* `-q` to set a quantity
* `-f` to set a filename to read a json with exchange endpoints from
* `-o` to determine the most optimal selection of orders to buy or sell. 

### Notes
* ##### This script defaults to a greedy order selection since it runs in `O(n)` worst case (where `n` is the number of orders) and `O(k)` average case where `k<<n` 
* ##### Refrain from using `-o` on an order book with more than 20 orders. The knapsack algorithm is used when the -o flag is set, and for really high orders, an optimal solution would be prohibitively expensive. 
