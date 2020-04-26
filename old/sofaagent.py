from __future__ import print_function

import os, sys

from win32con import *
from win32gui import *

import win32service
import win32serviceutil
import servicemanager
import win32event
import win32service

import subprocess

import time
import json
import win32con
import win32com.client
import win32com.server.policy
import win32api
import win32ts
import win32process
import win32security
import win32profile
import wmi
import win32pdh

import random

import uuid
import re
import subprocess

import urllib.request
from shutil import copyfile
import pythoncom
import logging
import sys
import ctypes
import asyncio
import keyboard
import datetime
import gmqtt
import socket
from gmqtt import Client as MQTTClient

SofaAgentVersion = 101018025


## from Sens.h
SENSGUID_PUBLISHER = "{5fee1bd6-5b9b-11d1-8dd2-00aa004abd5e}"
SENSGUID_EVENTCLASS_LOGON = "{d5978630-5b9f-11d1-8dd2-00aa004abd5e}"

## from EventSys.h
PROGID_EventSystem = "EventSystem.EventSystem"
PROGID_EventSubscription = "EventSystem.EventSubscription"

IID_ISensLogon = "{d597bab3-5b9f-11d1-8dd2-00aa004abd5e}"

class SensLogon(win32com.server.policy.DesignatedWrapPolicy):
    _com_interfaces_=[IID_ISensLogon]
    _public_methods_=[
        'Logon',
        'Logoff',
        'StartShell',
        'DisplayLock',
        'DisplayUnlock',
        'StartScreenSaver',
        'StopScreenSaver'
        ]

    def __init__(self, app):
        self.app=app
        self._wrap_(self)

    def Logon(self, *args):
        self.app.log.info('.. Log on event')
        asyncio.ensure_future(self.app.updateState('lockState','UNLOCKED'))

    def Logoff(self, *args):
        self.app.log.info('.. Log off event')
        asyncio.ensure_future(self.app.updateState('lockState','LOCKED'))

    def StartShell(self, *args):
        self.app.log.info('.. Start Shell event')

    def DisplayLock(self, *args):
        self.app.log.info('.. Display Lock event')
        asyncio.ensure_future(self.app.updateState('lockState','LOCKED'))

    def DisplayUnlock(self, *args):
        self.app.log.info('.. Display unlock event')
        asyncio.ensure_future(self.app.updateState('lockState','UNLOCKED'))

    def StartScreenSaver(self, *args):
        self.app.log.info('.. Start Screensaver event')

    def StopScreenSaver(self, *args):
        self.app.log.info('.. Stop Screensaver event')

class gmqttClient():

    def __init__(self, app):
        self.app=app
        #self.endpointId=self.app.devicePath.replace('/',':')
        self.deviceId=self.app.deviceId
        self.connected=False
        self.log = logging.getLogger('sofamqtt')
        self.log.info('.. MQTT Module initialized')
        self.topic='sofa/pc'
        self.broker='mqtt://home.dayton.home'
        self.broker='home.dayton.home'
        self.connected=False

    async def start(self):
        self.client = MQTTClient(self.deviceId)
        self.client.on_message = self.on_message
        self.client.on_connect = self.on_connect
        #self.client.set_auth_credentials(token, None)
        await self.client.connect(self.broker, 1883, version=gmqtt.constants.MQTTv311)
    
    def on_connect(self, client, flags, rc, properties):
        self.connected=True
        client.subscribe(self.topic, qos=0)
        self.sendState()

    def sendCommand(self,command):
        try:
            self.log.info('Sending command: %s' % command)
            self.client.publish(self.topic, json.dumps({'op':'command', 'device':self.app.deviceId, 'command':command }))
        except:
            self.log.error('Error sending command', exc_info=True)


    def sendState(self):
        try:
            self.client.publish(self.topic, json.dumps({'op':'state', 'device':self.app.deviceId, 'state': self.app.state }))
        except:
            self.log.error('Error sending state info', exc_info=True)

    def on_message(self, client, topic, payload, qos, properties):
        self.log.info('<< %s' % payload.decode())
        try:
            event=json.loads(payload)
        except:
            self.log.info('Message received but not JSON: %s' % payload)
            return False
        
        try:
            if 'op' in event:
                print('OP: %s' % event['op'])
                if event['op']=='discover':
                    self.sendState()
                    
                elif event['op']=='set':
                    if event['device']==self.deviceId:
                        asyncio.ensure_future(self.app.setState(event['property'], event['value']))

        except:
            self.log.error('Error handling message event: %s' % event, exc_info=True)


    async def notify(self, message, topic='pc'):

        try:
            if self.connected:
                self.log.info(">> mqtt/%s %s" % (self.topic, message))
                self.client.publish(self.topic, message)
            else:
                self.log.info('Notify called before connect')

        except:
            self.log.error('Error publishing message', exc_info=True)


class syslaunch():

    def __init__(self, app):
        self.app=app
        self.log = logging.getLogger('sofasyslaunch')
    
    def lockPC(self):
        ctypes.windll.user32.LockWorkStation()
         		        
    def suspendPC(self):
        
        self.log.info("+++ Local: Suspending PC")
        # Enable the SeShutdown privilege (which must be present in your
        # token in the first place)
        try:
            priv_flags = win32security.TOKEN_ADJUST_PRIVILEGES | win32security.TOKEN_QUERY
            hToken = win32security.OpenProcessToken (win32api.GetCurrentProcess (), priv_flags)
            priv_id = win32security.LookupPrivilegeValue (
                None, 
                win32security.SE_SHUTDOWN_NAME
            )
            old_privs = win32security.AdjustTokenPrivileges (
                hToken,
                0,
                [(priv_id, win32security.SE_PRIVILEGE_ENABLED)]
            )
            # Params:
            # True=> Standby; False=> Hibernate
            # True=> Force closedown; False=> Don't force
            ctypes.windll.kernel32.SetSystemPowerState (True, True)
        
        except: # catch *all* exceptions
            e = sys.exc_info()[1]
            self.log.info("Error: %s" % e )



class sofaPCAgent():
    
    def __init__(self, isrunning=False):

        self.isrunning=isrunning
        self.deviceId=socket.gethostname()
        self.filepath="C:\\Program Files\\SofaAgent"
        self.updatePollTime=6000
        self.lastUpdateCheck=datetime.datetime.now()

        pythoncom.CoInitialize()
        self.loop = asyncio.get_event_loop()
        self.adaptername='sofapc'
        self.logsetup('INFO',errorOnly=['gmqtt.mqtt.protocol','gmqtt.mqtt.handler','gmqtt.mqtt.package'])

        self.launch=syslaunch(self)
        self.mqttclient = gmqttClient(self)
        self.notify=self.mqttclient.notify
        #self.sendChangeReport=self.mqttclient.sendChangeReport
        self.log.info('-----------------')

    def logsetup(self, level="INFO", errorOnly=[]):
        
        loglevel=getattr(logging,level)
        logging.basicConfig(level=loglevel, format='%(asctime)-6s.%(msecs).03d %(levelname).1s %(lineno)4d %(threadName)-.1s: %(message)s',datefmt='%m/%d %H:%M:%S', filename='c:\\programdata\\%s.log' % self.adaptername,)
        self.log = logging.getLogger(self.adaptername)
        
        formatter = logging.Formatter('%(asctime)-6s.%(msecs).03d %(levelname).1s %(lineno)4d %(threadName)-.1s: %(message)s',datefmt='%m/%d %H:%M:%S')
        console = logging.StreamHandler()
        console.setFormatter(formatter)
        console.setLevel(logging.INFO)

        self.log.info('-- -----------------------------------------------')

        logging.getLogger(self.adaptername).addHandler(console)
        
        for lg in logging.Logger.manager.loggerDict:
            #self.log.info('.. Active logger: %s' % lg)
            for item in errorOnly:
                if lg.startswith(item):
                    self.log.info('.. Logger set to error and above: %s' % lg)
                    logging.getLogger(lg).setLevel(logging.ERROR)


    def initPowerEventMonitor(self):
        wc = WNDCLASS()
        wc.hInstance = hInst = GetModuleHandle(None)
        wc.lpszClassName = "PowerMonitor"
        wc.lpfnWndProc = self.WndProc
        self.classAtom = RegisterClass(wc)
        self.hWnd = CreateWindow(self.classAtom, "Power event monitor", 0, 0, 0, CW_USEDEFAULT, CW_USEDEFAULT, 0, 0, hInst, None)
        UpdateWindow(self.hWnd) 

    def requestLockState(self):  
        hwinsta = win32service.OpenWindowStation("winsta0", False, win32con.READ_CONTROL)
        hwinsta.SetProcessWindowStation()
        try:
            curr_desktop=win32service.OpenInputDesktop(0,True,win32con.MAXIMUM_ALLOWED)
            self.log.info('Requested Lock State: Unlocked')
            return 'UNLOCKED'

        except:
            self.log.info('Requested Lock State: Locked',exc_info=True)
            return 'LOCKED'

    def initSensEventMonitor(self):
        sl=SensLogon(self)
        subscription_interface=pythoncom.WrapObject(sl)
        event_system=win32com.client.Dispatch(PROGID_EventSystem)
        event_subscription=win32com.client.Dispatch(PROGID_EventSubscription)
        event_subscription.EventClassID=SENSGUID_EVENTCLASS_LOGON
        event_subscription.PublisherID=SENSGUID_PUBLISHER
        event_subscription.SubscriptionName='Python subscription'
        event_subscription.SubscriberInterface=subscription_interface
        event_system.Store(PROGID_EventSubscription, event_subscription)

    def initMediaKeys(self):
        keyboard.add_hotkey(-177, self.rewind, suppress=True) # unmute on keydown
        keyboard.add_hotkey(-176, self.ffw, suppress=True) # unmute on keydown
        keyboard.add_hotkey(-179, self.playpause, suppress=True) # unmute on keydown

    def playpause(self):
        self.log.info('loop %s' % self.loop)
        cmd=json.dumps({'op':'command', 'device':self.deviceId, 'command':'play' })
        asyncio.run_coroutine_threadsafe(self.notify(cmd), self.loop)

    def ffw(self):
        self.log.info('loop %s' % self.loop)
        cmd=json.dumps({'op':'command', 'device':self.deviceId, 'command':'skip' })
        asyncio.run_coroutine_threadsafe(self.notify(cmd), self.loop)

    def rewind(self):
        self.log.info('loop %s' % self.loop)
        cmd=json.dumps({'op':'command', 'device':self.deviceId, 'command':'rewind' })
        asyncio.run_coroutine_threadsafe(self.notify(cmd), self.loop)

    async def mainloop(self):

        await self.forwardevent('info','powermonitor Main Loop started.  Waiting for events.')
        while self.isrunning:
            pythoncom.PumpWaitingMessages()
            PumpWaitingMessages()
            await asyncio.sleep(.1)
            delta = datetime.datetime.now()-self.lastUpdateCheck
            if delta.seconds>self.updatePollTime:
                self.checkForUpdates()

            
    def checkForUpdates(self):
        try:
            self.log.info('Current Agent Version: %s' % SofaAgentVersion)
        except:
            self.log.error('Error showing version', exc_info=True)
            return False

        try:
            self.lastUpdateCheck=datetime.datetime.now()
            url = 'https://home.dayton.home/var/pc/agentversion'
            data = urllib.request.urlopen(url)
            versioninfo=data.read()
            serverversion=versioninfo.decode()
            self.log.info('Server Agent Version: %s' % serverversion)
            
            if str(SofaAgentVersion) != str(serverversion):
                try:
                    self.log.info('Downloading version %s' % serverversion)
                    url = 'https://home.dayton.home/var/pc/agent'
                    urllib.request.urlretrieve(url, "%s\sofaagent.py.new" % self.filepath)
                    self.log.info('New version %s available as %s' % (serverversion,"%s\sofaagent.py.new" % self.filepath))
                    copyfile("%s\sofaagent.py" % self.filepath, "%s\sofaagent.py.old" % self.filepath)
                    copyfile("%s\sofaagent.py.new" % self.filepath, "%s\sofaagent.py" % self.filepath)
                    
                    # attempt to restart service
                    DETACHED_PROCESS = 0x00000008
                    results = subprocess.Popen(['%s\sofa-restart.bat' % self.filepath], close_fds=True, creationflags=DETACHED_PROCESS)

                except:
                    self.log.error('Error updating to current version %s' % serverversion, exc_info=True)
        
        except:
            self.log.error('Error with Check for Update', exc_info=True)
            

    async def updateState(self, prop, value, sendChangeReport=True):
    
        try:
            self.log.info('updateState: %s %s' % (prop, value))
            self.log.info('curState: %s %s' % (sendChangeReport, self.state[prop]))
            if self.state[prop]!=value:
                self.state[prop]=value
                if sendChangeReport:
                    minichange={'op':'change', 'device':self.deviceId, 'property':prop, 'value':value}
                    self.log.info('sending change report: %s ' % minichange)
                    await self.notify(json.dumps(minichange))
        except:
            self.log.error('Error updating state: %s %s' % (prop, value), exc_info=True)
                
    async def setState(self, prop, value):
    
        if prop=='powerState':
            if value=="OFF":
                await self.updateState('lockState','LOCKED')
                await self.updateState('powerState','OFF')
                time.sleep(.5)
                self.launch.suspendPC()
                
        elif prop=='lockState':
            if value=="UNLOCKED":
                self.log.info('PC Unlock not implemented yet')
            elif value=="LOCKED":
                await self.updateState('lockState','LOCKED')
                self.launch.lockPC()
                

    def start(self):
        self.checkForUpdates()
        self.initPowerEventMonitor()
        self.initSensEventMonitor()
        self.initMediaKeys()
        self.state={ 'powerState' : 'ON', 'lockState' : self.requestLockState() }
        asyncio.set_event_loop(self.loop)
        self.loop.run_until_complete(self.mqttclient.start())
        self.loop.run_until_complete(self.mainloop())	

    async def forwardevent(self, eventType, event, data=''):
        self.log.info("%s - %s %s %s" % (str(datetime.datetime.now()), eventType, event, data))

    def stop(self):
        self.log.info('Sofa Agent Service is being stopped')
        self.loop.stop()
        self.loop.close()
        PostQuitMessage(0)

    def WndProc(self, hWnd, message, wParam, lParam):
        if message == WM_POWERBROADCAST:
            if wParam == PBT_APMSUSPEND:
                self.OnSuspend(hWnd, message, wParam, lParam)
            elif wParam == PBT_APMRESUMESUSPEND:
                self.OnResume(hWnd, message, wParam, lParam)
            elif wParam == PBT_APMRESUMEAUTOMATIC:
                self.OnAutoResume(hWnd, message, wParam, lParam)
            else:
                self.log.info("WMPB:"+str(wParam))

        elif message == WM_TIMECHANGE:
            asyncio.ensure_future(self.forwardevent("state","System Time Change Detected"))
        elif message == WM_SETTINGCHANGE:
            asyncio.ensure_future(self.forwardevent("state","Setting Change",str(wParam)+" "+str(lParam)))
        elif message == WM_DEVICECHANGE:
            asyncio.ensure_future(self.forwardevent("state","Device Change",str(wParam)+" "+str(lParam)))
        elif message == WM_CLOSE:
            asyncio.ensure_future(self.forwardevent("state","WM_CLOSE"))
            DestroyWindow(hWnd)
        elif message == WM_DESTROY:
            asyncio.ensure_future(self.forwardevent("state","WM_DESTROY"))
            PostQuitMessage(0)
        elif message == WM_QUERYENDSESSION:
            asyncio.ensure_future(self.forwardevent("APM.WM_QUERYENDSESSION"))
            return True
        else:
            logging.info("APM.unknown: "+str(message))
			
    def OnSuspend(self, hWnd, message, wParam, lParam):
        try:
            asyncio.ensure_future(self.updateState('lockState','LOCKED'))
            asyncio.ensure_future(self.updateState('powerState','OFF'))
            time.sleep(.5)
        except:
            self.log.error('Error handling suspend action', exc_info=Treu)

    def OnResume(self, hWnd, message, wParam, lParam):
        try:
            asyncio.ensure_future(self.forwardevent("state","resume"))
            asyncio.ensure_future(self.updateState('lockState','LOCKED'))
            asyncio.ensure_future(self.updateState('powerState','ON'))
        except:
            self.log.error('Error handling resume action', exc_info=Treu)

    def OnAutoResume(self, hWnd, message, wParam, lParam):
        try:
            asyncio.ensure_future(self.forwardevent("state","autoresume"))
            asyncio.ensure_future(self.updateState('lockState','LOCKED'))
            asyncio.ensure_future(self.updateState('powerState','ON'))
        except:
            self.log.error('Error handling autoresume action', exc_info=Treu)

class SMWinservice(win32serviceutil.ServiceFramework):
    '''Base class to create winservice in Python'''

    _svc_name_ = 'pythonService'
    _svc_display_name_ = 'Python Service'
    _svc_description_ = 'Python Service Description'

    @classmethod
    def parse_command_line(cls):
        '''
        ClassMethod to parse the command line
        '''
        win32serviceutil.HandleCommandLine(cls)

    def __init__(self, args):
        '''
        Constructor of the winservice
        '''
        win32serviceutil.ServiceFramework.__init__(self, args)
        self.hWaitStop = win32event.CreateEvent(None, 0, 0, None)
        socket.setdefaulttimeout(60)

    def SvcStop(self):
        '''
        Called when the service is asked to stop
        '''
        self.stop()
        self.ReportServiceStatus(win32service.SERVICE_STOP_PENDING)
        win32event.SetEvent(self.hWaitStop)

    def SvcDoRun(self):
        '''
        Called when the service is asked to start
        '''
        self.start()
        servicemanager.LogMsg(servicemanager.EVENTLOG_INFORMATION_TYPE,
                              servicemanager.PYS_SERVICE_STARTED,
                              (self._svc_name_, ''))
        self.main()

    def start(self):
        '''
        Override to add logic before the start
        eg. running condition
        '''
        pass

    def stop(self):
        '''
        Override to add logic before the stop
        eg. invalidating running condition
        '''
        pass

    def main(self):
        '''
        Main class to be ovverridden to add logic
        '''
        pass

class sofaAgentService(SMWinservice):

    _svc_name_ = "SofaAgent"
    _svc_display_name_ = "Sofa Control Agent"
    _svc_description_ = "Sofa MQTT control agent"

    def stop(self):
        self.isrunning = False
        self.agent.stop()

    def start(self):
        self.isrunning = True

    def main(self):
        self.agent=sofaPCAgent(self.isrunning)
        self.agent.start()

# entry point of the module: copy and paste into the new module
# ensuring you are calling the "parse_command_line" of the new created class
if __name__ == '__main__':
    #isrunning=True
    #agent=sofaPCAgent(isrunning)
    #agent.start()

    print(sys.argv)
    sofaAgentService.parse_command_line()

