#!/usr/bin/python
# -*- coding: utf-8 -*-

import sys
import configargparse
import uuid
import os
import json
from datetime import datetime, timedelta
import logging
import shutil
import requests

import httplib2
import requests
import simplejson as json
import smtplib


from importlib import import_module
from s2sphere import LatLng, CellId
from geopy.geocoders import GoogleV3

from . import config

log = logging.getLogger(__name__)


def parse_unicode(bytestring):
    decoded_string = bytestring.decode(sys.getfilesystemencoding())
    return decoded_string


def verify_config_file_exists(filename):
    fullpath = os.path.join(os.path.dirname(__file__), filename)
    if not os.path.exists(fullpath):
        log.info('Could not find %s, copying default', filename)
        shutil.copy2(fullpath + '.example', fullpath)


def get_args():
    # fuck PEP8
    configpath = os.path.join(os.path.dirname(__file__), '../config/config.ini')
    parser = configargparse.ArgParser(default_config_files=[configpath])
    parser.add_argument('-a', '--auth-service', type=str.lower, action='append',
                        help='Auth Services, either one for all accounts or one per account. \
                        ptc or google. Defaults all to ptc.')
    parser.add_argument('-u', '--username', action='append',
                        help='Usernames, one per account.')
    parser.add_argument('-p', '--password', action='append',
                        help='Passwords, either single one for all accounts or one per account.')
    parser.add_argument('-l', '--location', type=parse_unicode,
                        help='Location, can be an address or coordinates')
    parser.add_argument('-st', '--step-limit', help='Steps', type=int,
                        default=12)
    parser.add_argument('-sd', '--scan-delay',
                        help='Time delay between requests in scan threads',
                        type=float, default=10)
    parser.add_argument('-ld', '--login-delay',
                        help='Time delay between each login attempt',
                        type=float, default=5)
    parser.add_argument('-lr', '--login-retries',
                        help='Number of logins attempts before refreshing a thread',
                        type=int, default=3)
    parser.add_argument('-sr', '--scan-retries',
                        help='Number of retries for a given scan cell',
                        type=int, default=5)
    parser.add_argument('-dc', '--display-in-console',
                        help='Display Found Pokemon in Console',
                        action='store_true', default=False)
    parser.add_argument('-H', '--host', help='Set web server listening host',
                        default='127.0.0.1')
    parser.add_argument('-P', '--port', type=int,
                        help='Set web server listening port', default=5000)
    parser.add_argument('-L', '--locale',
                        help='Locale for Pokemon names (default: {},\
                        check {} for more)'.
                        format(config['LOCALE'], config['LOCALES_DIR']), default='en')
    parser.add_argument('-c', '--china',
                        help='Coordinates transformer for China',
                        action='store_true')
    parser.add_argument('-d', '--debug', help='Debug Mode', action='store_true')
    parser.add_argument('-m', '--mock',
                        help='Mock mode. Starts the web server but not the background thread.',
                        action='store_true', default=False)
    parser.add_argument('-ns', '--no-server',
                        help='No-Server Mode. Starts the searcher but not the Webserver.',
                        action='store_true', default=False)
    parser.add_argument('-os', '--only-server',
                        help='Server-Only Mode. Starts only the Webserver without the searcher.',
                        action='store_true', default=False)
    parser.add_argument('-nsc','--no-search-control',
                        help='Disables search control',
                        action='store_false', dest='search_control', default=True)
    parser.add_argument('-fl', '--fixed-location',
                        help='Hides the search bar for use in shared maps.',
                        action='store_true', default=False)
    parser.add_argument('-k', '--gmaps-key',
                        help='Google Maps Javascript API Key',
                        required=True)
    parser.add_argument('-C', '--cors', help='Enable CORS on web server',
                        action='store_true', default=False)
    parser.add_argument('-D', '--db', help='Database filename',
                        default='pogom.db')
    parser.add_argument('-cd', '--clear-db',
                        help='Deletes the existing database before starting the Webserver.',
                        action='store_true', default=False)
    parser.add_argument('-np', '--no-pokemon',
                        help='Disables Pokemon from the map (including parsing them into local db)',
                        action='store_true', default=False)
    parser.add_argument('-ng', '--no-gyms',
                        help='Disables Gyms from the map (including parsing them into local db)',
                        action='store_true', default=False)
    parser.add_argument('-nk', '--no-pokestops',
                        help='Disables PokeStops from the map (including parsing them into local db)',
                        action='store_true', default=False)
    parser.add_argument('--db-type', help='Type of database to be used (default: sqlite)',
                        default='sqlite')
    parser.add_argument('--db-name', help='Name of the database to be used')
    parser.add_argument('--db-user', help='Username for the database')
    parser.add_argument('--db-pass', help='Password for the database')
    parser.add_argument('--db-host', help='IP or hostname for the database')
    parser.add_argument('--db-port', help='Port for the database', type=int, default=3306)
    parser.add_argument('--db-max_connections', help='Max connections for the database', type=int, default=5)
    parser.add_argument('-wh', '--webhook', help='Define URL(s) to POST webhook information to',
                        nargs='*', default=False, dest='webhooks')
    parser.add_argument('-pf', '--profile',
                        help='Set the profile, include emails to notify and interested Pokemons to to load',
                        default='profile.json')
    parser.set_defaults(DEBUG=False)

    args = parser.parse_args()

    if args.only_server:
        if args.location is None:
            parser.print_usage()
            print sys.argv[0] + ': error: arguments -l/--location is required'
            sys.exit(1)
    else:
        errors = []

        if (args.username is None):
            errors.append('Missing `username` either as -u/--username or in config')

        if (args.location is None):
            errors.append('Missing `location` either as -l/--location or in config')

        if (args.password is None):
            errors.append('Missing `password` either as -p/--password or in config')

        if (args.step_limit is None):
            errors.append('Missing `step_limit` either as -st/--step-limit or in config')

        if args.auth_service is None:
            args.auth_service = ['ptc']

        num_auths = len(args.auth_service)
        num_usernames = len(args.username)
        num_passwords = len(args.password)
        if num_usernames > 1:
            if num_passwords > 1 and num_usernames != num_passwords:
                errors.append('The number of provided passwords ({}) must match the username count ({})'.format(num_passwords, num_usernames))
            if num_auths > 1 and num_usernames != num_auths:
                errors.append('The number of provided auth ({}) must match the username count ({})'.format(num_auths, num_usernames))

        if len(errors) > 0:
            parser.print_usage()
            print sys.argv[0] + ": errors: \n - " + "\n - ".join(errors)
            sys.exit(1)

        # Fill the pass/auth if set to a single value
        if num_passwords == 1:
            args.password = [ args.password[0] ] * num_usernames
        if num_auths == 1:
            args.auth_service = [ args.auth_service[0] ] * num_usernames

        # Make our accounts list
        args.accounts = []

        # Make the accounts list
        for i, username in enumerate(args.username):
            args.accounts.append({'username': username, 'password': args.password[i], 'auth_service': args.auth_service[i]})

    return args


def insert_mock_data(position):
    num_pokemon = 6
    num_pokestop = 6
    num_gym = 6

    log.info('Creating fake: %d pokemon, %d pokestops, %d gyms',
        num_pokemon, num_pokestop, num_gym)

    from .models import Pokemon, Pokestop, Gym
    from .search import generate_location_steps

    latitude, longitude = float(position[0]), float(position[1])

    locations = [l for l in generate_location_steps((latitude, longitude), num_pokemon)]
    disappear_time = datetime.now() + timedelta(hours=1)

    detect_time = datetime.now()

    for i in range(1, num_pokemon):
        Pokemon.create(encounter_id=uuid.uuid4(),
                       spawnpoint_id='sp{}'.format(i),
                       pokemon_id=(i+1) % 150,
                       latitude=locations[i][0],
                       longitude=locations[i][1],
                       disappear_time=disappear_time,
                       detect_time=detect_time)

    for i in range(1, num_pokestop):
        Pokestop.create(pokestop_id=uuid.uuid4(),
                        enabled=True,
                        latitude=locations[i+num_pokemon][0],
                        longitude=locations[i+num_pokemon][1],
                        last_modified=datetime.now(),
                        # Every other pokestop be lured
                        lure_expiration=disappear_time if (i % 2 == 0) else None,
                        active_pokemon_id=i
                        )

    for i in range(1, num_gym):
        Gym.create(gym_id=uuid.uuid4(),
                   team_id=i % 3,
                   guard_pokemon_id=(i+1) % 150,
                   latitude=locations[i + num_pokemon + num_pokestop][0],
                   longitude=locations[i + num_pokemon + num_pokestop][1],
                   last_modified=datetime.now(),
                   enabled=True,
                   gym_points=1000
                   )

def i8ln(word):
    if config['LOCALE'] == "en":
        return word
    if not hasattr(i8ln, 'dictionary'):
        file_path = os.path.join(
            config['ROOT_PATH'],
            config['LOCALES_DIR'],
            '{}.min.json'.format(config['LOCALE']))
        if os.path.isfile(file_path):
            with open(file_path, 'r') as f:
                i8ln.dictionary = json.loads(f.read())
        else:
            log.warning('Skipping translations - Unable to find locale file: %s', file_path)
            return word
    if word in i8ln.dictionary:
        return i8ln.dictionary[word]
    else:
        log.debug('Unable to find translation for "%s" in locale %s!', word, config['LOCALE'])
        return word

def get_pokemon_data(pokemon_id):
    if not hasattr(get_pokemon_data, 'pokemon'):
        file_path = os.path.join(
            config['ROOT_PATH'],
            config['DATA_DIR'],
            'pokemon.min.json')

        with open(file_path, 'r') as f:
            get_pokemon_data.pokemon = json.loads(f.read())
    return get_pokemon_data.pokemon[str(pokemon_id)]

def get_pokemon_name(pokemon_id):
    return i8ln(get_pokemon_data(pokemon_id)['name'])

def get_pokemon_rarity(pokemon_id):
    return i8ln(get_pokemon_data(pokemon_id)['rarity'])

def get_pokemon_types(pokemon_id):
    pokemon_types = get_pokemon_data(pokemon_id)['types']
    return map(lambda x: {"type": i8ln(x['type']), "color": x['color']}, pokemon_types)

def send_to_webhook(message_type, message):
    args = get_args()

    data = {
        'type': message_type,
        'message': message
    }

    if args.webhooks:
        webhooks = args.webhooks

        for w in webhooks:
            try:
                requests.post(w, json=data, timeout=(None, 1))
            except requests.exceptions.ReadTimeout:
                log.debug('Response timeout on webhook endpoint %s', w)
            except requests.exceptions.RequestException as e:
                log.debug(e)

def get_encryption_lib_path():
    lib_path = ""
    if sys.platform == "win32":
        lib_path = os.path.join(os.path.dirname(__file__), "encrypt.dll")
    elif sys.platform == "darwin":
        lib_path = os.path.join(os.path.dirname(__file__), "libencrypt-osx.so")
    elif sys.platform.startswith('linux'):
        lib_path = os.path.join(os.path.dirname(__file__), "libencrypt.so")
    else:
        err = "Unexpected/unsupported platform '{}'".format(sys.platform)
        log.error(err)
        raise Exception(err)

    if not os.path.isfile(lib_path):
        err = "Could not find {} encryption library {}".format(sys.platform, lib_path)
        log.error(err)
        raise Exception(err)

    return lib_path

def load_profile():
    filename = 'profile.json'
    if get_args().profile:
        filename = get_args().profile
    file_path = os.path.dirname(os.path.realpath('runserver.py')) + '/' + filename

    with open(file_path) as f:
        profile = json.loads(f.read())

        if not profile['emails']:
            raise ImportError('No notification emails in profile.json.')
        else:
            email_to = profile['emails']

        if not profile['interested_pokemons']:
            raise ImportError('No interested Pokenmon IDs specified in profile.json.')
        else:
            interested = profile['interested_pokemons']
        return email_to, interested


def send_email(username, password, email_to, message):
    try:
        server = smtplib.SMTP("smtp.gmail.com", 587)
        server.ehlo()
        server.starttls()
        server.login(username, password)
        server.sendmail(username, email_to, message.encode('utf-8').strip())
        server.close()
        log.info('successfully sent the mail')
    except:
        log.error("failed to send mail: " + password)

def shurl(longUrl):
    API_KEY = 'AIzaSyDIledAeDEV0TytxRu9UkCEILIOlmrhiL0'
    try:
        API_KEY
    except NameError:
        apiUrl = 'https://www.googleapis.com/urlshortener/v1/url'
    else:
        apiUrl = 'https://www.googleapis.com/urlshortener/v1/url?key=%s' % API_KEY

    headers = {"Content-type": "application/json"}
    data = {"longUrl": longUrl}
    h = httplib2.Http('.cache')
    try:
        headers, response = h.request(apiUrl, "POST", json.dumps(data), headers)
        short_url = json.loads(response)['id']

    except Exception, e:
        print "unexpected error %s" % e
    return short_url