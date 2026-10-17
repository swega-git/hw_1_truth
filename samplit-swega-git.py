import random
import sys 


def main():
    if len(sys.argv) < 2:                   # accept a single filename as a command-line argument
        sys.exit(1)

    file_name = sys.argv[1]

    with open(file_name, 'r') as f:         # read the file line by line 
        for line in f:
            if random.random() < 0.01:      # Randomly select each line with 1% probability 
                print(line, end='')         # print to stdout


if __name__ == "__main__":
    main()



