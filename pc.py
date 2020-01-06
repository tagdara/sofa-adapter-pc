#!/usr/bin/python3

import sys, os
# Add relative paths for the directory where the adapter is located as well as the parent
sys.path.append(os.path.dirname(__file__))
sys.path.append(os.path.join(os.path.dirname(__file__),'../../base'))

from sofabase import sofabase
from sofabase import adapterbase
import devices

import json
import asyncio
import concurrent.futures
import datetime
import uuid
import socket
import struct

class pcServer(sofabase):

    class EndpointHealth(devices.EndpointHealth):

        @property            
        def connectivity(self):
            return 'OK'

    class PowerController(devices.PowerController):

        @property            
        def powerState(self):
            return self.nativeObject['powerState']

        async def TurnOn(self, correlationToken='', **kwargs):
            try:
                # should probably check to see if the machine is on, and if so also send the command so that
                # things like unlock or wake-from-just-monitor-sleep will work without WOL
                if self.deviceid in self.adapter.dataset.config['cachedMacAddresses']:
                    self.adapter.wakeonlan(self.adapter.dataset.config['cachedMacAddresses'][self.deviceid])
                    return self.device.Response(correlationToken)
                else:
                    self.adapter.log.info('Did not find MAC address for %s in %s' % ( self.deviceid, self.adapter.dataset.config['cachedMacAddresses']))
                    return {}
            except:
                self.adapter.log.error('!! Error during TurnOn', exc_info=True)
        
        async def TurnOff(self, correlationToken='', **kwargs):
            try:
                cmd={"op":"set", "property":"powerState", "value":"OFF", 'device': self.deviceid }
                self.adapter.notify('sofa/pc', json.dumps(cmd)) 
                return self.device.Response(correlationToken)
            except:
                self.adapter.log.error('!! Error during TurnOff', exc_info=True)

    class LockController(devices.LockController):
        
        @property            
        def lockState(self):
            return self.nativeObject['lockState']
 
        async def Lock(self, correlationToken='', **kwargs):

            try:
                cmd={"op":"set", "property":"lockState", "value":"LOCKED", 'device': self.deviceid }
                self.adapter.notify('sofa/pc', json.dumps(cmd))
                return self.device.Response(correlationToken)
            except:
                self.adapter.log.error('!! Error during Lock', exc_info=True)

        async def Unlock(self, correlationToken='', **kwargs):
            try:
                cmd={"op":"set", "property":"lockState", "value":"UNLOCKED", 'device': self.deviceid }
                self.adapter.notify('sofa/pc', json.dumps(cmd))
                return self.device.Response(correlationToken)
            except:
                self.adapter.log.error('!! Error during Unlock', exc_info=True)
   

    class adapterProcess():
        def __init__(self, log=None, loop=None, dataset=None, notify=None, request=None, **kwargs):
            self.dataset=dataset
            self.dataset.nativeDevices['desktop']={}

            #self.definitions=definitions.Definitions
            self.adapterTopics=['sofa/pc']
            self.log=log
            self.notify=notify
            if not loop:
                self.loop = asyncio.new_event_loop()
            else:
                self.loop=loop
            
        async def start(self):
            self.log.info('.. Starting PC Manager')
            try:
                if 'cachedDevices' in self.dataset.config:
                    for dev in self.dataset.config['cachedDevices']:
                        await self.dataset.ingest({"desktop": { dev : self.dataset.config['cachedDevices'][dev] }}) 

            except:
                self.log.error('Error loading cached devices', exc_info=True)
                
            self.notify('sofa/pc','{"op":"discover"}')
            
        # MQTT Adapter Specific Overlays
        async def processAdapterTopicMessage(self, topic, payload):
        
            try:
                self.log.info('Adapter MQTT Data received on topic %s: %s' % (topic,payload))
                try:
                    message=json.loads(payload)
                except json.decoder.JSONDecodeError:
                    self.log.error('Non JSON data received.')
                    return False
                    
                
                if 'op' in message:
                    if message['op']=='state':
                        await self.dataset.ingest({"desktop": { message['device'] : message['state'] }})        

                    if message['op']=='change':
                        await self.dataset.ingest({"desktop": { message['device'] : { message['property']: message['value'] }}})        
                    
                    if message['op']=='command':
                        if message['command'] in ['Skip','Play','Rewind','Pause']:
                            command={
                                "directive": {
                                    "header": {
                                        "namespace": "Alexa.MusicController",
                                        "name": message['command'],
                                        "payloadVersion": "3",
                                        "messageId": str(uuid.uuid1()),
                                        "correlationToken": str(uuid.uuid1())
                                    },
                                    "endpoint": {
                                        "scope": {
                                            "type": "BearerToken",
                                            "token": "access-token-from-skill"
                                        },
                                        "endpointId": "sonos:player:RINCON_B8E937ECE1F001400",
                                        "cookie": {}
                                    },
                                    "payload": {}
                                }
                            }
                            await self.dataset.sendDirectiveToAdapter(command)
                            #await self.dataset.requestAlexaStateChange(command)
                        
            except:
                self.log.error('Error handling Adapter MQTT Data', exc_info=True)



        # Adapter Overlays that will be called from dataset
        async def addSmartDevice(self, path):
            
            try:
                if path.split("/")[1]=="desktop":
                    deviceid=path.split("/")[2]    
                    nativeObject=self.dataset.getObjectFromPath(self.dataset.getObjectPath(path))
                    if deviceid not in self.dataset.localDevices:
                        device=devices.alexaDevice('pc/desktop/%s' % deviceid, nativeObject['name'], displayCategories=['PC'], adapter=self)
                        device.PowerController=pcServer.PowerController(device=device)
                        device.LockController=pcServer.LockController(device=device)
                        return self.dataset.newaddDevice(device)
                return False
                
            except:
                self.log.error('Error defining smart device', exc_info=True)
                return False

        async def virtualList(self, itempath, query={}):

            try:
                if itempath=="agentversion":
                    try:
                        with open(os.path.join(os.path.dirname(__file__), 'sofaagent.py'),'r') as agentfile:
                            line = agentfile.readline()
                            version='0000'
                            while line and version=='0000':
                                if line.startswith('SofaAgentVersion = '):
                                    version=line[19:].strip('\n').strip('\r')
                                line = agentfile.readline()
                    
                            self.log.info('Current Agent Version is: %s' % version )
                            return version
                    except:
                        self.log.error('Error determining Agent Version',exc_info=True)
                        return "0000"

                if itempath=="agent":
                    try:
                        with open(os.path.join(os.path.dirname(__file__), 'sofaagent.py'),'r') as agentfile:
                            return agentfile.read()
                    except:
                        self.log.error("Error loading agent file" ,exc_info=True)
                        return ""
            
            except:
                self.log.error('Error getting virtual list for %s' % itempath, exc_info=True)



        def wakeonlan(self, macaddress):
        
            try:
                if len(macaddress) == 17: # mac address has unwanted separators
                    macaddress = macaddress.replace(macaddress[2], '')
 
                # Pad the synchronization stream.
                data = ''.join(['FFFFFFFFFFFF', macaddress * 20])
                send_data = b''
                # Split up the hex values and pack.
                for i in range(0, len(data), 2):
                    send_data = b''.join([send_data, struct.pack('B', int(data[i: i + 2], 16))])
                # Broadcast it to the LAN.
                sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
                sock.sendto(send_data, ('<broadcast>', 7))    
                self.log.info('>> Wake-on-LAN magic packet sent to '+str(macaddress))
            except:
                self.log.error('Error sending Wake On LAN packet: %s' % macaddress, exc_info=True)



if __name__ == '__main__':
    adapter=pcServer(name='pc')
    adapter.start()