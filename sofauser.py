
import os
import socket
import sys
import json
import pythoncom
import asyncio
import logging
import datetime
import win32api
import win32con
import win32gui_struct
import win32gui
import gmqtt
import keyboard

from gmqtt import Client as MQTTClient
from win32con import *
from win32gui import *

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
        self.client = MQTTClient(self.deviceId+"-user")
        self.client.on_message = self.on_message
        self.client.on_connect = self.on_connect
        #self.client.set_auth_credentials(token, None)
        await self.client.connect(self.broker, 1883, version=gmqtt.constants.MQTTv311)
    
    def on_connect(self, client, flags, rc, properties):
        self.connected=True
        client.subscribe(self.topic, qos=0)
        #self.sendState()

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
        
        print('<< %s' % payload.decode())
        self.log.info('<< %s' % payload.decode())
        try:
            event=json.loads(payload)
        except:
            self.log.info('Message received but not JSON: %s' % payload)
            return False


    async def notify(self, message, topic='pc'):

        try:
            if self.connected:
                self.log.info(">> mqtt/%s %s" % (self.topic, message))
                self.client.publish(self.topic, message)
            else:
                self.log.info('Notify called before connect')

        except:
            self.log.error('Error publishing message', exc_info=True)


class SysTrayIcon(object):
    '''TODO'''
    QUIT = 'QUIT'
    SPECIAL_ACTIONS = [QUIT]

    FIRST_ID = 1023

    def __init__(self,
                 icon,
                 hover_text,
                 menu_options,
                 on_quit=None,
                 default_menu_index=None,
                 window_class_name=None,):

        self.icon = icon
        self.hover_text = hover_text
        self.on_quit = on_quit

        menu_options = menu_options + (('Quit', None, self.QUIT),)
        self._next_action_id = self.FIRST_ID
        self.menu_actions_by_id = set()
        self.menu_options = self._add_ids_to_menu_options(list(menu_options))
        self.menu_actions_by_id = dict(self.menu_actions_by_id)
        del self._next_action_id


        self.default_menu_index = (default_menu_index or 0)
        self.window_class_name = window_class_name or "SysTrayIconPy"

        message_map = {win32gui.RegisterWindowMessage("TaskbarCreated"): self.restart,
                       win32con.WM_DESTROY: self.destroy,
                       win32con.WM_COMMAND: self.command,
                       win32con.WM_USER+20 : self.notify,}
        # Register the Window class.
        window_class = win32gui.WNDCLASS()
        hinst = window_class.hInstance = win32gui.GetModuleHandle(None)
        window_class.lpszClassName = self.window_class_name
        window_class.style = win32con.CS_VREDRAW | win32con.CS_HREDRAW;
        window_class.hCursor = win32gui.LoadCursor(0, win32con.IDC_ARROW)
        window_class.hbrBackground = win32con.COLOR_WINDOW
        window_class.lpfnWndProc = message_map # could also specify a wndproc.
        classAtom = win32gui.RegisterClass(window_class)
        # Create the Window.
        style = win32con.WS_OVERLAPPED | win32con.WS_SYSMENU
        self.hwnd = win32gui.CreateWindow(classAtom,
                                          self.window_class_name,
                                          style,
                                          0,
                                          0,
                                          win32con.CW_USEDEFAULT,
                                          win32con.CW_USEDEFAULT,
                                          0,
                                          0,
                                          hinst,
                                          None)
        win32gui.UpdateWindow(self.hwnd)
        self.notify_id = None
        self.refresh_icon()

    def non_string_iterable(self,obj):
        try:
            iter(obj)
        except TypeError:
            return False
        else:
            return not isinstance(obj, str)

    def _add_ids_to_menu_options(self, menu_options):
        result = []
        for menu_option in menu_options:
            option_text, option_icon, option_action = menu_option
            if callable(option_action) or option_action in self.SPECIAL_ACTIONS:
                self.menu_actions_by_id.add((self._next_action_id, option_action))
                result.append(menu_option + (self._next_action_id,))
            elif self.non_string_iterable(option_action):
                result.append((option_text,
                               option_icon,
                               self._add_ids_to_menu_options(option_action),
                               self._next_action_id))
            else:
                print('Unknown item', option_text, option_icon, option_action)
            self._next_action_id += 1
        return result

    def refresh_icon(self):
        # Try and find a custom icon
        hinst = win32gui.GetModuleHandle(None)
        if os.path.isfile(self.icon):
            icon_flags = win32con.LR_LOADFROMFILE | win32con.LR_DEFAULTSIZE
            hicon = win32gui.LoadImage(hinst,
                                       self.icon,
                                       win32con.IMAGE_ICON,
                                       0,
                                       0,
                                       icon_flags)
        else:
            print("Can't find icon file - using default.")
            hicon = win32gui.LoadIcon(0, win32con.IDI_APPLICATION)

        if self.notify_id: message = win32gui.NIM_MODIFY
        else: message = win32gui.NIM_ADD
        self.notify_id = (self.hwnd,
                          0,
                          win32gui.NIF_ICON | win32gui.NIF_MESSAGE | win32gui.NIF_TIP,
                          win32con.WM_USER+20,
                          hicon,
                          self.hover_text)
        win32gui.Shell_NotifyIcon(message, self.notify_id)

    def restart(self, hwnd, msg, wparam, lparam):
        self.refresh_icon()

    def destroy(self, hwnd, msg, wparam, lparam):
        if self.on_quit: self.on_quit(self)
        nid = (self.hwnd, 0)
        win32gui.Shell_NotifyIcon(win32gui.NIM_DELETE, nid)
        win32gui.PostQuitMessage(0) # Terminate the app.

    def notify(self, hwnd, msg, wparam, lparam):
        if lparam==win32con.WM_LBUTTONDBLCLK:
            self.execute_menu_option(self.default_menu_index + self.FIRST_ID)
        elif lparam==win32con.WM_RBUTTONUP:
            self.show_menu()
        elif lparam==win32con.WM_LBUTTONUP:
            pass
        return True

    def show_menu(self):
        menu = win32gui.CreatePopupMenu()
        self.create_menu(menu, self.menu_options)
        #win32gui.SetMenuDefaultItem(menu, 1000, 0)

        pos = win32gui.GetCursorPos()
        # See http://msdn.microsoft.com/library/default.asp?url=/library/en-us/winui/menus_0hdi.asp
        win32gui.SetForegroundWindow(self.hwnd)
        win32gui.TrackPopupMenu(menu,
                                win32con.TPM_LEFTALIGN,
                                pos[0],
                                pos[1],
                                0,
                                self.hwnd,
                                None)
        win32gui.PostMessage(self.hwnd, win32con.WM_NULL, 0, 0)

    def create_menu(self, menu, menu_options):
        for option_text, option_icon, option_action, option_id in menu_options[::-1]:
            if option_icon:
                option_icon = self.prep_menu_icon(option_icon)

            if option_id in self.menu_actions_by_id:                
                item, extras = win32gui_struct.PackMENUITEMINFO(text=option_text,
                                                                hbmpItem=option_icon,
                                                                wID=option_id)
                win32gui.InsertMenuItem(menu, 0, 1, item)
            else:
                submenu = win32gui.CreatePopupMenu()
                self.create_menu(submenu, option_action)
                item, extras = win32gui_struct.PackMENUITEMINFO(text=option_text,
                                                                hbmpItem=option_icon,
                                                                hSubMenu=submenu)
                win32gui.InsertMenuItem(menu, 0, 1, item)

    def prep_menu_icon(self, icon):
        # First load the icon.
        ico_x = win32api.GetSystemMetrics(win32con.SM_CXSMICON)
        ico_y = win32api.GetSystemMetrics(win32con.SM_CYSMICON)
        hicon = win32gui.LoadImage(0, icon, win32con.IMAGE_ICON, ico_x, ico_y, win32con.LR_LOADFROMFILE)

        hdcBitmap = win32gui.CreateCompatibleDC(0)
        hdcScreen = win32gui.GetDC(0)
        hbm = win32gui.CreateCompatibleBitmap(hdcScreen, ico_x, ico_y)
        hbmOld = win32gui.SelectObject(hdcBitmap, hbm)
        # Fill the background.
        brush = win32gui.GetSysColorBrush(win32con.COLOR_MENU)
        win32gui.FillRect(hdcBitmap, (0, 0, 16, 16), brush)
        # unclear if brush needs to be feed.  Best clue I can find is:
        # "GetSysColorBrush returns a cached brush instead of allocating a new
        # one." - implies no DeleteObject
        # draw the icon
        win32gui.DrawIconEx(hdcBitmap, 0, 0, hicon, ico_x, ico_y, 0, 0, win32con.DI_NORMAL)
        win32gui.SelectObject(hdcBitmap, hbmOld)
        win32gui.DeleteDC(hdcBitmap)

        return hbm

    def command(self, hwnd, msg, wparam, lparam):
        id = win32gui.LOWORD(wparam)
        self.execute_menu_option(id)

    def execute_menu_option(self, id):
        menu_action = self.menu_actions_by_id[id]      
        if menu_action == self.QUIT:
            win32gui.DestroyWindow(self.hwnd)
        else:
            menu_action(self)

class sofaPCUser():

    def __init__(self, isrunning=False):

        self.isrunning=isrunning
        self.deviceId=socket.gethostname()
        self.filepath="C:\\Program Files\\SofaAgent"
        self.updatePollTime=6000
        self.lastUpdateCheck=datetime.datetime.now()

        self.loop = asyncio.get_event_loop()
        self.adaptername='sofapc'
        self.logsetup('INFO',errorOnly=['xgmqtt.mqtt.protocol','xgmqtt.mqtt.handler','xgmqtt.mqtt.package'])

        self.mqttclient = gmqttClient(self)
        self.notify=self.mqttclient.notify
        #self.sendChangeReport=self.mqttclient.sendChangeReport
        self.log.info('-----------------')
        self.pause=True

    def logsetup(self, level="INFO", errorOnly=[]):
        
        loglevel=getattr(logging,level)
        logdir=os.environ['USERPROFILE']
        logging.basicConfig(level=loglevel, format='%(asctime)-6s.%(msecs).03d %(levelname).1s %(lineno)4d %(threadName)-.1s: %(message)s',datefmt='%m/%d %H:%M:%S', filename='%s\\%s.log' % (logdir, self.adaptername),)
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

    def initMediaKeys(self):
        keyboard.add_hotkey(-177, self.rewind, suppress=True) # unmute on keydown
        keyboard.add_hotkey(-176, self.skip, suppress=True) # unmute on keydown
        keyboard.add_hotkey(-179, self.playpause, suppress=True) # unmute on keydown

    def hello(self, sysTrayIcon=None): 
        print("Hello World.")

    def simon(self, sysTrayIcon=None): 
        print("Hello Simon.")

    def playpause(self, sysTrayIcon=None):
        self.log.info('loop %s' % self.loop)
        if self.pause:
            cmd=json.dumps({'op':'command', 'device':self.deviceId, 'command':'Pause' })
            self.pause=False
        else:
            cmd=json.dumps({'op':'command', 'device':self.deviceId, 'command':'Play' })
            self.pause=True
        asyncio.run_coroutine_threadsafe(self.notify(cmd), self.loop)

    def skip(self, sysTrayIcon=None):
        cmd=json.dumps({'op':'command', 'device':self.deviceId, 'command':'Skip' })
        asyncio.run_coroutine_threadsafe(self.notify(cmd), self.loop)

    def rewind(self, sysTrayIcon=None):
        self.log.info('loop %s' % self.loop)
        cmd=json.dumps({'op':'command', 'device':self.deviceId, 'command':'Rewind' })
        asyncio.run_coroutine_threadsafe(self.notify(cmd), self.loop)

    def bye(self, sysTrayIcon=None): 
        print('Bye, then.')
        self.isrunning=False

    def start(self):
        self.icon = "./sofa.ico"
        self.hover_text = "SysTrayIcon.py Demo"
        self.menu = (('Playpause', self.icon, self.playpause),
                    ('Skip', self.icon, self.skip),
                    ('A sub-menu', self.icon, (
                        ('Say Hello to Simon', self.icon, self.simon),
                        ('Say Hello', self.icon, self.hello),
                    ))
                )
        SysTrayIcon(self.icon, self.hover_text, self.menu, on_quit=self.bye, default_menu_index=1)

        self.initMediaKeys()
        asyncio.set_event_loop(self.loop)
        self.loop.run_until_complete(self.mqttclient.start())
        self.loop.run_until_complete(self.mainloop())	
    
    async def mainloop(self):

        print('here')
        while self.isrunning:
            PumpWaitingMessages()
            await asyncio.sleep(.1)


# Minimal self test. You'll need a bunch of ICO files in the current working
# directory in order for this to work...
if __name__ == '__main__':
    isrunning=True
    useragent=sofaPCUser(isrunning)
    useragent.start()

    