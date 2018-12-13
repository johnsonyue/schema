# NOTE:
 - run sections with `*`, only when new monitors and broker&backend are needed

# add new monitors monitor*
 - modify `db.json` and `secrets.json`

# setup monitors*
 - `./setup.sh`
 - NOTE: setup of each monitor were logged: to `$(pwd)/<$monitor_id>.setup.log`

# setup broker and backend*
 - prerequisites:
   - broker and backend must be deployed on a monitor with a public IP address
   - set corresponding inbound rules to allow access to ports
 - setup:
   - `./run.sh ssh setup-broker -n <$monitor_id>`
   - `./run.sh ssh setup-backend -n <$monitor_id>`
 - postsetup:
   - modify `/etc/redis/redis.conf`, set bind-address's value to the public IP
   - modify `/etc/mysql/mysql.conf.d/mysqld.cnf`, same as above

# add manager info:
 - modify `db.json` and `secrets.json`, add "Manager" as if it's a monitor
 - modify `import.py`, change `host_ip`, `server_ip`, `server_port` to corresponding value

# setup manager
 - apt-get install -y expect
 - `./run.sh ssh mkdirs -n Manager` ( add signature to trusted hosts )
 - `./run.sh ssh setup-manager -n Manager`

# run measurement:
 - run via shell: `python run.py <$config_filepath>`
 - run via socket:

        # start socket server, (on a seperate terminal)
        root# python svr.py

        # to start a measurement task
        root# nc <$host_ip> <$host_port>
        {"action": "start_task", "url": "<$config_fileurl>"}
        
        # to query the state of a task
        # <$task_id> := $(echo $config_fileurl | sed 's/\.conf$/g')
        root# nc <$host_ip> <$host_port>
        {"action": "query_task", "task_id": "<$task_id>"}
