from mycroft import MycroftSkill, intent_file_handler
from adapt.intent import IntentBuilder
from mycroft.messagebus.message import Message
from mycroft.util.log import LOG
import httplib2
from googleapiclient import discovery
import sys
from tzlocal import get_localzone
from datetime import datetime, timedelta
from mycroft.util.parse import extract_datetime
from requests import HTTPError

from .mft_token_cred import MycroftTokenCredentials
UTC_TZ = u'+00:00'
def nice_time(dt, lang="en-us", speech=True, use_24hour=False,
              use_ampm=False):
    if use_24hour:
        string = dt.strftime("%H:%M")
    else:
        if use_ampm:
            string = dt.strftime("%I:%M %p")
        else:
            string = dt.strftime("%I:%M")
        if string[0] == '0':
            string = string[1:] 
        return string

    if not speech:
        return string
    
    if use_24hour:
        speak = ""

        if string[0] == '0':
            if string[1] == '0':
                speak = "0 0"
            else:
                speak = "0 " + string[1]
        else:
            speak += string[0:2]

        if string[3] == '0':
            if string[4] == '0':
                speak += " oclock" 
            else:
                speak += " o " + string[4]  
        else:
            if string[0] == '0':
                speak += " " + string[3:5]
            else:
                speak += ":" + string[3:5]

        return speak
    else:
        if lang.startswith("en"):
            if dt.hour == 0 and dt.minute == 0:
                return "midnight" 
            if dt.hour == 12 and dt.minute == 0:
                return "noon"  
         
        return string
    
def today_reserve(d):
    return d.date() == datetime.today().date()

def tomorrow_reserve(d):
    return d.date() == datetime.today().date() + timedelta(days=1)

def fullday_reserve(e):
    return 'dateTime' not in e['start']

def remove_tz(string):
    return string[:-6]


class Reservation(MycroftSkill):
    def __init__(self):
        MycroftSkill.__init__(self)
        super(Reservation, self).__init__('Reservation')
        
   @property
    def use_24hour(self):
        return self.config_core.get('time_format') == 'full'
        
    def credentials(self, msg=None):
        argv = sys.argv
        sys.argv = []
        try:
            self.credentials = MycroftTokenCredentials(3)
            LOG.info('Credentials: {}'.format(self.credentials))
            http = self.credentials.authorize(httplib2.Http())
            self.service = discovery.build('calendar', 'v3', http=http)
            sys.argv = argv
            self.register_intents()
            self.cancel_scheduled_reserve('credentials')
        except HTTPError:
            LOG.info('No Credentials available')
            pass
        
    def reserve_intents(self):
        intent = IntentBuilder('NextReserveIntent')\
            .require('NextKeyword')\
            .one_of('ReserveKeyword', 'ScheduleKeyword')\
            .build()
        self.register_intent(intent, self.get_next)

        intent = IntentBuilder('DaysReserveIntent')\
            .require('QueryKeyword')\
            .one_of('ReserveKeyword', 'ScheduleKeyword')\
            .build()
        self.register_intent(intent, self.get_day)

        intent = IntentBuilder('FirstReserveIntent')\
            .one_of('ReserveKeyword', 'ScheduleKeyword')\
            .require('FirstKeyword')\
            .build()
        self.register_intent(intent, self.get_first)

    def initialize(self):
        self.schedule_reserve(self.credentials, datetime.now(),
                            name='credentials')

        
    def get_next(self, msg=None):
        now = datetime.utcnow().isoformat() + 'Z'  
        reservationResult = self.service.events().list(
            calendarId='primary', timeMin=now, maxResults=10,
            singleEvents=True, orderBy='startTime').execute()
        reserve = reservationResult.get('items', [])

        if not events:
            self.speak_dialog('NoNextReservations')
        else:
            event = events[0]
            LOG.debug(event)
            if not fullday_reserve(event):
                start = event['start'].get('dateTime')
                d = datetime.strptime(remove_tz(start), '%Y-%m-%dT%H:%M:%S')
                starttime = nice_time(d, self.lang, True, self.use_24hour,
                                      True)
                startdate = d.strftime('%-d %B')
            else:
                start = event['start']['date']
                d = datetime.strptime(start, '%Y-%m-%d')
                startdate = d.strftime('%-d %B')
                starttime = None
            
            if starttime is None:
                if d.date() == datetime.today().date():
                    dt = {'event': event['summary']}
                    self.speak_dialog('NextReserveInToday', dt)
                elif tomorrow_event(d):
                    dt = {'event': event['summary']}
                    self.speak_dialog('NextReserveInTomorrow', dt)
                else:
                    dt = {'event': event['summary'],
                            'date': startdate}
                    self.speak_dialog('NextReserveInThisDay', dt)
            elif d.date() == datetime.today().date():
                dt = {'event': event['summary'],
                        'time': starttime}
                self.speak_dialog('NextReserve', dt)
            elif tomorrow_event(d):
                dt = {'event': event['summary'],
                        'time': starttime}
                self.speak_dialog('NextReserveTomorrow', dt)
            else:
                dt = {'event': event['summary'],
                        'time': starttime,
                        'date': startdate}
                self.speak_dialog('NextReserveDate', dt)
                
     def speak_info(self, start, stop, max_results=None):
        reservationResult = self.service.events().list(
            calendarId='primary', timeMin=start, timeMax=stop,
            singleEvents=True, orderBy='startTime',
            maxResults=max_results).execute()
        reserve = reservationResult.get('items', [])
        if not events:
            LOG.debug(start)
            d = datetime.strptime(start.split('.')[0], '%Y-%m-%dT%H:%M:%SZ')
            if today_event(d):
                self.speak_dialog('NoReserveToday')
            elif tomorrow_event(d):
                self.speak_dialog('NoReserveTomorrow')
            else:
                self.speak_dialog('NoReserve')
        else:
            for e in events:
                if fullday_reserve(e):
                    dt = {'event': e['summary']}
                    self.speak_dialog('DayReserve', dt)
                else:
                    start = e['start'].get('dateTime', e['start'].get('date'))
                    d = datetime.strptime(remove_tz(start),
                                             '%Y-%m-%dT%H:%M:%S')
                    starttime = nice_time(d, self.lang, True, self.use_24hour,
                                          True)
                    if today_reserve(d) or tomorrow_reserve(d) or True:
                        dt = {'event': e['summary'],
                                'time': starttime}
                        self.speak_dialog('NextReserve', dt)   
                
                
    def get_day(self, msg=None):
        d = extract_datetime(msg.data['utterance'])[0]
        d = d.replace(hour=0, minute=0, second=1, tzinfo=None)
        d_lt = d.replace(hour=23, minute=59, second=59, tzinfo=None)
        d = d.isoformat() + 'Z'
        d_lt = d_lt.isoformat() + 'Z'
        self.speak_info(d, d_lt)
        return
    
    def get_first(self, msg=None):
        d = extract_datetime(msg.data['utterance'])[0]
        d = d.replace(hour=0, minute=0, second=1, tzinfo=None)
        d_lt = d.replace(hour=23, minute=59, second=59, tzinfo=None)
        d = d.isoformat() + 'Z'
        d_lt = d_lt.isoformat() + 'Z'
        self.speak_info(d, d_lt, max_results=1)
        
    @property
    def utc_time(self):
        return timedelta(seconds=self.location['timezone']['offset'] / 1000)
    
    @intent_file_handler('ScheduleReserve.intent')
    def add_newreserve(self, message=None):
        subject = self.get_response('whatsTheNewEvent')
        start = self.get_response('whenDoesEventStart')
        end = self.get_response('whenDoesEventEnd')
        if subject and start and end:
            ft = extract_datetime(start)
            le = extract_datetime(end)
            if ft and le:
                ft = ft[0] - self.utc_time
                le = le[0] - self.utc_time
                self.create_reserve(subject, start_time=ft, end_time=le)
                
    @intent_file_handler('ScheduleAtReserve.intent')
    def add_newreserve_sd(self, msg=None):
        subject = msg.data.get('eventsubject', None)
        if subject is None:
            self.log.debug("NO SUBJECT")
            return

        te = extract_datetime(msg.data['utterance'])[0] 
        te -= timedelta(seconds=self.location['timezone']['offset'] / 1000)
        et = te + timedelta(hours=1)
        self.create_reserve(subject, te, et)
        
    @intent_file_handler('ScheduleInReserve.intent')
    def add_newreserve_st(self, msg=None):
        subject = msg.data.get('addReserveAtThisTime')
        te = extract_datetime(msg.data['utterance'])[0]
        te += timedelta(seconds=self.location['timezone']['offset'] / 1000)
        et = te + 30*te
        self.create_reserve(subject, te, et)
        
    @intent_file_handler('DeleteReserve.intent')
    def add_deletereserve(self, message=None):
        subject = self.get_response('whatEventToBeDeleted')
        self.delete_event(subject)
        
    def create_reserve(self, subject, start_time, end_time, summary=None):
        start_time = start_time.strftime('%Y-%m-%dT%H:%M:00')
        stop_time = end_time.strftime('%Y-%m-%dT%H:%M:00')
        stop_time += UTC_TZ
        event = {}
        event['summary'] = subject
        event['start'] = {
            'dateTime': start_time,
            'timeZone': 'UTC'
        }
        event['end'] = {
            'dateTime': stop_time,
            'timeZone': 'UTC'
        }
        data = {'event': subject}
        try:
            self.service.events()\
                .insert(calendarId='primary', body=event).execute()
            self.speak_dialog('SuccessfullyAddedEvent', data)
        except:
            self.speak_dialog('FailedAddingEvent', data)
            
    def delete_reserve(self, subject, summary=None):
        data = {'event': subject}
        try:
            self.service.events()\
                .delete(calendarId='primary', body=event).execute()
            self.speak_dialog('SuccessfullyDeletedEvent', data)
        except:
            self.speak_dialog('FailedDeletingEvent', data)
        
    @intent_file_handler('reservation.intent')
    def handle_reservation(self, message):
        self.speak_dialog('reservation')


def create_skill():
    return Reservation()

