import pickle
from uuid import uuid4
import threading
import select
import traceback
import json

import sqlalchemy as sa

import psycopg2

from transcriber.models import WorkTable
from transcriber.app_config import DB_CONN

try:
    from raven import Client
    client = Client(dsn=WORKER_SENTRY)
except ImportError: # pragma: no cover
    client = None
except KeyError:
    client = None

def queuefunc(f):

    def delay(*args, **kwargs):
        
        engine = sa.create_engine(DB_CONN)
        
        pickled_task = pickle.dumps((f, args, kwargs))
        key = str(uuid4())

        task_name = f.__name__
        
        query_args = {
            'key': key,
            'value': pickled_task,
            'task_name': task_name,
        }
        
        with engine.begin() as conn:
            conn.execute(sa.text(''' 
                INSERT INTO work_table
                    (key, work_value, task_name, updated, claimed) 
                VALUES ( 
                  :key, 
                  :value, 
                  :task_name, 
                  NOW(),
                  FALSE
                )
            '''), **query_args)
            
            conn.execute("NOTIFY worker, '{}'".format(key))
        
        return key

    f.delay = delay
    return f

class ProcessMessage(threading.Thread):
    stopper = None

    def __init__(self, stopper):
        super().__init__()
        
        engine = sa.create_engine(DB_CONN)
        
        self.engine = engine
        self.stopper = stopper
        
        self.conn = self.engine.raw_connection()
        self.conn.set_isolation_level(psycopg2.extensions.ISOLATION_LEVEL_AUTOCOMMIT)
        
        curs = self.conn.cursor()
        curs.execute('LISTEN worker;')
        
        print('Listening for messages...')

    def run(self):
        while not self.stopper.is_set():
            if not select.select([self.conn],[],[],5) == ([],[],[]):
                
                self.conn.poll()
                
                while self.conn.notifies:
                    notify = self.conn.notifies.pop(0)
                    
                    work = self.getWork(notify.payload)
                    
                    if work:
                        self.doWork(work)
    
    def getWork(self, work_key):
        
        with self.engine.begin() as trans:
            
            upd = '''
                UPDATE work_table SET 
                  claimed = TRUE,
                  updated = NOW()
                FROM (
                  SELECT * FROM work_table
                  WHERE key = :work_key
                    AND claimed = FALSE
                  FOR UPDATE
                ) AS s
                WHERE work_table.key = s.key
                RETURNING work_table.*
            '''
            work = trans.execute(sa.text(upd), 
                                 work_key=work_key).first()
        
        return work

    def doWork(self, work):
        
        func, args, kwargs = pickle.loads(work.work_value)
        
        upd_args = {
            'key': work.key,
            'completed': True,
        }

        try:
            upd_args['return_value'] = func(*args, **kwargs)
            upd_args['cleared'] = True
            upd_args['tb'] = None
        except Exception as e:

            try:
                upd_args['return_value'] = {'message': e.message}
            except AttributeError:
                upd_args['return_value'] = {'message': str(e)}

            if client: # pragma: no cover
                client.captureException()
            
            upd_args['tb'] = traceback.format_exc()
            print(upd_args['tb'])

            upd_args['completed'] = False
            upd_args['cleared'] = True
            upd_args['return_value'] = json.dumps(upd_args['return_value'])

        upd = ''' 
               UPDATE work_table SET
                  traceback = :tb,
                  return_value = :return_value,
                  updated = NOW(),
                  completed = :completed,
                  cleared = :cleared
                WHERE key = :key
              '''
        with self.engine.begin() as conn:
            conn.execute(sa.text(upd), **upd_args)

def queue_daemon(): # pragma: no cover
    # import logging
    # logging.getLogger().setLevel(logging.WARNING)
    
    import signal
    import sys

    engine = sa.create_engine(DB_CONN)
    
    work_table = WorkTable.__table__
    work_table.create(engine, checkfirst=True)
   
    stopper = threading.Event()

    worker = ProcessMessage(stopper)

    def signalHandler(signum, frame):
        stopper.set()
        worker.join()
        sys.exit(0)

    signal.signal(signal.SIGINT, signalHandler)

    print('Starting worker')
    worker.start()
