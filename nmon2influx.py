#!/usr/bin/env python3


# TPEP import AIX nmon file to influxdb

import paramiko
import io
import argparse
import re
import configparser
import time
import pprint
import os


from influxdb import InfluxDBClient

class NMON_Import:

    def __init__(self,skip,only,influx_dbhost="127.0.0.1",influx_dbname="nmon",influx_dbport=8086):
        self.skip=skip
        self.only=only
        self.lines_pattern=['^AAA','^BBBP','^VG.+|^PAGING|^WLM|^NET|^NPIV|^SEA|^IOADAPT|^LAN','^LPAR|^CPU_ALL|^MEM|^MEMNEW|^MEMUSE|^PAGE|^FILE|^PROC|^PCPU_ALL|^SCPU_ALL','^TOP','^ZZZZ','^UARG','^PROCAIO','^.CPU[0-9]+|^CPU[0-9]+','^DISK.+','^SUMMARY']
        self.lines_proc=[self.proc_info,self.proc_BBBP,self.proc_label_value,self.proc_metrics,self.proc_top,self.proc_zzzz,self.proc_uarg,self.proc_skip,self.proc_xcpuxx,self.proc_hdisk,self.proc_summary]
        self.host=""
        self.serial=""
        self.debug=0
        self.metric=dict()
        self.json_body=[];
        self.col_name=dict()
        self.zzzz=dict()
        self.labels=dict()
        self.version=0
        self.hdiskinfo=dict()

        self.influx_client=InfluxDBClient(influx_dbhost,influx_dbport,database=influx_dbname);
        

    def proc_info(self,line):
        line_tab=line.split(',')
        if (re.match('host',line_tab[1])):
            self.host=line_tab[2].strip();
        if (re.match('Serial',line_tab[1])):
            self.serial=line_tab[2].strip();
        if (re.match('AIX',line_tab[1])):
            self.version=line_tab[2].strip();

    def proc_BBBP(self,line):
        if (re.search('m hdisk',line)):
            hdisk=re.search('"m (hdisk[0-9]+) .*"',line).group(1).strip()
            hdisk_type=re.search('".*-L[0-9]+\s+(.*)"',line).group(1).strip()
            self.hdiskinfo[hdisk]=hdisk_type
            if (self.debug):
                print ("hdisk: "+hdisk+" hdisk_type: "+self.hdiskinfo[hdisk])
            
            
    def proc_label_value(self,line):
        r=line.replace(',,',',0,')
        line_tab=r.strip().split(',')
        if line_tab[0] in self.metric:
            line_tab[1]=self.zzzz[line_tab[1]]
            epoch=int(time.mktime(time.strptime(line_tab[1],"%d-%b-%YT%H:%M:%SZ")))
            for i in range(len(self.labels[line_tab[0]])):
                self.json_body.append( {
                    "measurement":line_tab[0],
                    "tags": {
                        "serial":self.serial,
                        "host":self.host,
                        "label":self.labels[line_tab[0]][i]
                    },
                    "time":epoch,
                    "fields" : {
                        "value" : float(line_tab[i+2])
                    }
                })
        else:
            self.metric[line_tab[0]]=True;
            self.labels[line_tab[0]]=[];
            for i in iter(line_tab[2:]):
                self.labels[line_tab[0]].append(i.strip())


    def proc_hdisk(self,line):
        r=line.replace(',,',',0,')
        line_tab=r.strip().split(',')
        if line_tab[0] in self.metric:
            line_tab[1]=self.zzzz[line_tab[1]]
            epoch=int(time.mktime(time.strptime(line_tab[1],"%d-%b-%YT%H:%M:%SZ")))
            for i in range(len(self.labels[line_tab[0]])):
                if (self.labels[line_tab[0]][i] in self.hdiskinfo):
                    hdisk_type=self.hdiskinfo[self.labels[line_tab[0]][i]]
                else:
                    hdisk_type="Unknow"
                    
                self.json_body.append( {
                    "measurement":line_tab[0],
                    "tags": {
                        "serial":self.serial,
                        "host":self.host,
                        "label":self.labels[line_tab[0]][i],
                        "type":hdisk_type
                    },
                    "time":epoch,
                    "fields" : {
                        "value" : float(line_tab[i+2])
                    }
                })
        else:
            self.metric[line_tab[0]]=True;
            self.labels[line_tab[0]]=[];
            for i in iter(line_tab[2:]):
                self.labels[line_tab[0]].append(i.strip())

                

    def proc_xcpuxx(self,line):
        r=line.replace(',,',',0,')
        line_tab=r.strip().split(',')
        fields=dict()
        cpu_id=re.search('^[PS]*CPU([0-9]+),.*',line).group(1).strip()
        cpu_type=re.search('(^[PS]*CPU)[0-9]+,.*',line).group(1).strip()

        if cpu_type in self.metric and (re.match("T[0-9]+",line_tab[1])):
            line_tab[1]=self.zzzz[line_tab[1]]
            epoch=int(time.mktime(time.strptime(line_tab[1],"%d-%b-%YT%H:%M:%SZ")))
            l=len(self.col_name[cpu_type])
            for i in range(l):
                fields[self.col_name[cpu_type][i]]=float(line_tab[i+2])
            self.json_body.append( {
                "measurement":cpu_type,
                "tags": {
                    "serial":self.serial,
                    "host":self.host,
                    "id":cpu_id
                },
                "time":epoch,
                "fields" : fields
            })
        else:
            self.metric[cpu_type]=True;
            self.col_name[cpu_type]=line_tab[2:]
                   
        
    def proc_metrics(self,line):
        r=line.replace(',,',',0,')
        line_tab=r.strip().split(',')
        fields=dict()
        if line_tab[0] in self.metric:
            line_tab[1]=self.zzzz[line_tab[1]]
            l=len(self.col_name[line_tab[0]])
            for i in range(l-1):
                fields[self.col_name[line_tab[0]][i]]=float(line_tab[i+2])
            epoch=int(time.mktime(time.strptime(line_tab[1],"%d-%b-%YT%H:%M:%SZ")))
                        
            self.json_body.append( {
                "measurement":line_tab[0],
                "tags": {
                    "serial":self.serial,
                    "host":self.host
                },
                "time":epoch,
                "fields" : fields
            })
        else:
            self.metric[line_tab[0]]=True;
            self.col_name[line_tab[0]]=line_tab[2:]
            
                        
        
    def proc_top(self,line):
        line_tab=line.strip().split(',')
        fields=dict()
        if line_tab[0] in self.metric and re.match("[0-9]+",line_tab[1]):
            line_tab[2]=self.zzzz[line_tab[2]]
            epoch=int(time.mktime(time.strptime(line_tab[2],"%d-%b-%YT%H:%M:%SZ")))
            l=len(self.col_name[line_tab[0]])
            for i in range(l-3):
                fields[self.col_name[line_tab[0]][i]]=float(line_tab[i+3])

            self.json_body.append( {
                "measurement":line_tab[0],
                "tags": {
                    "serial":self.serial,
                    "host":self.host,
                    "cmd":line_tab[13],
		    "pid":line_tab[1]
                },
                "time":epoch,
                "fields" : fields
            })
        else:
            self.metric[line_tab[0]]=True
            self.col_name[line_tab[0]]=line_tab[3:]
            

    def proc_summary(self,line):
        r=line.replace(',,',',0,')
        rr=r.replace(', ,',',0,')
        line_tab=rr.strip().split(',')
        fields=dict()
        line_tab[1]=self.zzzz[line_tab[1]]

        if line_tab[0] in self.metric:
            l=len(self.col_name[line_tab[0]])
            for i in range(l-2):
                fields[self.col_name[line_tab[0]][i]]=float(line_tab[i+2])
                epoch=int(time.mktime(time.strptime(line_tab[1],"%d-%b-%YT%H:%M:%SZ")))
                
            self.json_body.append( {
                "measurement":line_tab[0],
                "tags": {
                    "serial":self.serial,
                    "host":self.host,
                    "cmd":line_tab[-1]
                },
                "time":epoch,
                "fields" : fields
            })
        else:
            self.metric[line_tab[0]]=True;
            self.col_name[line_tab[0]]=line_tab[2:]

            

    def proc_uarg(self,line):
        r=line.replace(',,',',0,')
        line_tab=r.strip().split(',')
        fields=dict()
        print ("UARG:" + line)
        
        if line_tab[0] in self.metric:
            if (re.search("THCNT",line)):
                pass
            else:
                line_tab[1]=self.zzzz[line_tab[1]]
                l=len(self.col_name[line_tab[0]])

                epoch=int(time.mktime(time.strptime(line_tab[1],"%d-%b-%YT%H:%M:%SZ")))
                
                fields['THCOUNT']=0
                
                self.json_body.append( {
                    "measurement":line_tab[0],
                    "tags": {
                        "serial":self.serial,
                        "host":self.host,
                        "pid":line_tab[2],
                        "ppid":line_tab[3],
                        "cmd":line_tab[4],
                        "user":line_tab[6],
                        "group":line_tab[7],
                        "FullCmd":line_tab[8]
                    },
                    "time":epoch,
                    "fields" : fields
                })
        else:
            self.metric[line_tab[0]]=True;
            self.col_name[line_tab[0]]=line_tab[2:]

    def proc_zzzz(self,line):
        line_tab=line.split(',')
        self.zzzz[line_tab[1]]=line_tab[3].strip()+"T"+line_tab[2].strip()+"Z";

    def proc_skip(self,line):
        if (self.debug):
            print ("Skip:",line)

    def parse_line(self,line):
        for pattern,case in zip(self.lines_pattern,self.lines_proc):
            if (re.search(pattern,line)):
                case(line)

    def flush(self):
        self.influx_client.write_points(self.json_body,time_precision='s',batch_size=65535);
        self.json_body=[];
        
    def parse_file(self,file):
        self.metric=dict()
        self.zzzz=dict()
        self.labels=dict()
        self.hdiskinfo=dict()
        
        for line in iter(file):
            if (re.match("^ZZZZ|^AAA|^BBB",line)):
                if (self.debug):
                    print ("ZZZZ:",line)
                self.parse_line(line)
            elif (self.only):
                if (re.match(self.only.strip(),line)):
                    if (self.debug):
                        print ("Only:",line)
                    self.parse_line(line)
                else:
                    pass                
            elif (self.skip and (re.match(self.skip.strip(),line))):
                if (self.debug):
                    print ("Skip:",line)
            else:
                if (self.debug):
                    print ("Parse:",line)
                self.parse_line(line)
        self.flush()
                
                


config = configparser.ConfigParser()
config.read(os.environ['HOME']+"/.nmon2influx.ini")

parser = argparse.ArgumentParser()
parser.add_argument("--skip", help="Skip Regexp",default=config.get('MAIN','skip',fallback=None))
parser.add_argument("--only", help="Only Tab Regexp",default=config.get('MAIN','only',fallback=None))
parser.add_argument("--influx_host",help="Influx Database Host",default=config.get('DB','host',fallback="127.0.0.1"))
parser.add_argument("--influx_name",help="Influx Database Nmon",default=config.get('DB','name',fallback="nmon"))
parser.add_argument("--influx_port",help="Influx Database Port Default 8086",default=config.get('DB','port',fallback="8086"))
parser.add_argument("--dbuser",help="Postgres Database user",default=config.get('DB','username',fallback="nmon"))
parser.add_argument("--dbpass",help="Postgres Database password",default=config.get('DB','password',fallback="nmon"))
parser.add_argument("--ssh_host",help="ssh hostname for remote connection",default=config.get('SSH','hosts',fallback=None))
parser.add_argument("--ssh_username",help="ssh username for remote connection",default=config.get('SSH','username',fallback=None))
parser.add_argument("--ssh_password",help="ssh password for remote connection",default=config.get('SSH','password',fallback=None));
parser.add_argument("--ssh_keyfile",help="ssh key file for remote connection",default=config.get('SSH','keyfile',fallback=None));
parser.add_argument("--ssh_file",help="ssh remote file");
parser.add_argument("--proxy",help="ssh proxy conexion like bastion",default=config.get('SSH','proxy',fallback=None))
parser.add_argument("-f",type=argparse.FileType('r'), nargs='+');
args = parser.parse_args()


dbhost=args.influx_host
dbuser=args.dbuser
dbpass=args.dbpass
dbname=args.influx_name
dbport=args.influx_port


NMON=NMON_Import(skip=args.skip,only=args.only,influx_dbhost=dbhost,influx_dbname=dbname,influx_dbport=dbport);

# Set proxy ssh config if avaible

sock_proxy=None

if (args.f is None and args.ssh_host):
    host_list=args.ssh_host.split(',')
    for host in iter(host_list):
        ssh=paramiko.SSHClient()
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())

        try:
            print  ("Connect to "+host)
            if (args.proxy):
                sock_proxy=paramiko.ProxyCommand("ssh user@"+args.proxy+" nc "+host+" 22")
                
            if (args.ssh_keyfile):
                ssh.connect(host,username=args.ssh_username,key_filename=args.ssh_keyfile)
            else:
                ssh.connect(host,username=args.ssh_username,password=args.ssh_password,sock=sock_proxy)
            stdin, stdout, stderr = ssh.exec_command("ls "+args.ssh_file);
            
            #    stdout=ssh.get_cmd_output("ls "+args.ssh_file);
            #print (stdout)
            for f in iter(stdout):
                print("import "+host+" file:'"+f.strip()+"'");
                ftp = ssh.open_sftp()
                ftp.get(f.strip(),'/tmp/tmp_nmon2pg')
                ftp.close()
                remote_file=open('/tmp/tmp_nmon2pg',encoding='latin1')
                NMON.parse_file(remote_file)
                remote_file.close()
            ssh.close()
        except Exception as e:
            print (e)
            print ("Can not ssh connect to "+host);
            NMON.flush();
            pass
else:
    if (args.f):
        for nmon_file in args.f:
            NMON.parse_file(nmon_file)
            nmon_file.close();
