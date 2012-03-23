#!/bin/sh
mysql -u root -D blojsom -h localhost -e "TRUNCATE Comment;"
python /home/ec2-user/bench.py 127.0.0.1:80 $*
