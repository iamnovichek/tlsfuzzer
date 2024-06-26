# Author: Hubert Kario, (c) 2020
# Released under Gnu GPL v2.0, see LICENSE file for details

"""Minimal test for verifying server-selected DH parameters"""

from __future__ import print_function
import traceback
import sys
import getopt
from itertools import chain
from random import sample

from tlslite.constants import CipherSuite, AlertLevel, AlertDescription, \
        ExtensionType
from tlslite.extensions import \
        SignatureAlgorithmsExtension, SignatureAlgorithmsCertExtension
from tlslite.mathtls import FFDHE_PARAMETERS
import tlslite.dh as dh
from tlsfuzzer.runner import Runner
from tlsfuzzer.messages import Connect, ClientHelloGenerator, \
        ClientKeyExchangeGenerator, ChangeCipherSpecGenerator, \
        FinishedGenerator, ApplicationDataGenerator, AlertGenerator
from tlsfuzzer.expect import ExpectServerHello, ExpectCertificate, \
        ExpectServerHelloDone, ExpectChangeCipherSpec, ExpectFinished, \
        ExpectAlert, ExpectClose, ExpectServerKeyExchange, \
        ExpectApplicationData
from tlsfuzzer.utils.lists import natural_sort_keys
from tlsfuzzer.helpers import RSA_SIG_ALL, AutoEmptyExtension

import time
from constants import CHARACTERS_LENGTH

version = 3


def help_msg():
    print("Usage: <script-name> [-h hostname] [-p port] [[probe-name] ...]")
    print(" -h hostname    name of the host to run the test against")
    print("                localhost by default")
    print(" -p port        port number to use for connection, 4433 by default")
    print(" probe-name     if present, will run only the probes with given")
    print("                names and not all of them, e.g \"sanity\"")
    print(" -e probe-name  exclude the probe from the list of the ones run")
    print("                may be specified multiple times")
    print(" -x probe-name  expect the probe to fail. When such probe passes despite being marked like this")
    print("                it will be reported in the test summary and the whole script will fail.")
    print("                May be specified multiple times.")
    print(" -X message     expect the `message` substring in exception raised during")
    print("                execution of preceding expected failure probe")
    print("                usage: [-x probe-name] [-X exception], order is compulsory!")
    print(" -n num         run 'num' or all(if 0) tests instead of default(all)")
    print("                (excluding \"sanity\" tests)")
    print(" --named-ffdh   Name of the well-known FFDHE parameters that the server can use")
    print("                can be used multiple times to specify multiple valid groups")
    print("                \"RFC7919 ffdhe2048\" by default, unless --dhparam used")
    print(" --dhparam      File with the expected DH parameters that the server should use")
    print("                can be used together with --named-ffdh to specify multiple")
    print("                acceptable parameters")
    print(" -t timeout     how long to wait before assuming the server won't")
    print("                send a message")
    print(" -M | --ems     Enable support for Extended Master Secret")
    print(" --help         this message")


def main():
    """Test what DH parameters server selects for exchange"""
    host = "localhost"
    port = 4433
    num_limit = None
    run_exclude = set()
    expected_failures = {}
    last_exp_tmp = None
    group_names = []
    dh_file = None
    timeout = 5.0
    ems = False
    
    print("=" * CHARACTERS_LENGTH)
    print("Test to check if server selects the expected DH parameters".upper())
    print("See tlslite.mathtls.FFDHE_PARAMETERS for supported names".upper())
    print("=" * CHARACTERS_LENGTH)
    time.sleep(3)

    argv = sys.argv[1:]
    opts, args = getopt.getopt(argv, "h:p:e:x:X:t:n:M",
                               ["help", "named-ffdh=", "ems",
                                "dhparam="])
    for opt, arg in opts:
        if opt == '-h':
            host = arg
        elif opt == '-p':
            port = int(arg)
        elif opt == '-e':
            run_exclude.add(arg)
        elif opt == '-x':
            expected_failures[arg] = None
            last_exp_tmp = str(arg)
        elif opt == '-X':
            if not last_exp_tmp:
                raise ValueError("-x has to be specified before -X")
            expected_failures[last_exp_tmp] = str(arg)
        elif opt == '-n':
            num_limit = int(arg)
        elif opt == '--help':
            help_msg()
            sys.exit(0)
        elif opt == '--named-ffdh':
            group_names.append(arg)
        elif opt == '--dhparam':
            dh_file = arg
        elif opt == '-M' or opt == '--ems':
            ems = True
        elif opt == '-t':
            timeout = float(arg)
        else:
            raise ValueError("Unknown option: {0}".format(opt))

    if args:
        run_only = set(args)
    else:
        run_only = None

    if not group_names and not dh_file:
        group_names = ["RFC7919 ffdhe2048"]

    try:
        valid_params = set(FFDHE_PARAMETERS[i] for i in group_names)
    except KeyError as e:
        raise ValueError(
            "Unrecognised group name: {0}, known names: {1}"
            .format(str(e),
                ", ".join("'{0}'".format(i) for i in
                          FFDHE_PARAMETERS.keys())))

    if dh_file:
        with open(dh_file, "r") as f:
            data = f.read()
        valid_params.add(dh.parse(data))

    conversations = {}

    conversation = Connect(host, port, timeout=timeout)
    node = conversation
    ext = {ExtensionType.renegotiation_info: None}
    if ems:
        ext[ExtensionType.extended_master_secret] = AutoEmptyExtension()
    ciphers = [CipherSuite.TLS_DHE_RSA_WITH_AES_128_CBC_SHA,
               CipherSuite.TLS_DHE_RSA_WITH_AES_256_CBC_SHA,
               CipherSuite.TLS_DHE_RSA_WITH_AES_128_GCM_SHA256,
               CipherSuite.TLS_DHE_RSA_WITH_AES_128_CBC_SHA256]
    ext[ExtensionType.signature_algorithms] = \
        SignatureAlgorithmsExtension().create(RSA_SIG_ALL)
    ext[ExtensionType.signature_algorithms_cert] = \
        SignatureAlgorithmsCertExtension().create(RSA_SIG_ALL)
    node = node.add_child(ClientHelloGenerator(ciphers, extensions=ext))
    srv_ext = {ExtensionType.renegotiation_info:None}
    if ems:
        srv_ext[ExtensionType.extended_master_secret] = None
    node = node.add_child(ExpectServerHello(extensions=srv_ext))
    node = node.add_child(ExpectCertificate())
    node = node.add_child(ExpectServerKeyExchange())
    node = node.add_child(ExpectServerHelloDone())
    node = node.add_child(ClientKeyExchangeGenerator())
    node = node.add_child(ChangeCipherSpecGenerator())
    node = node.add_child(FinishedGenerator())
    node = node.add_child(ExpectChangeCipherSpec())
    node = node.add_child(ExpectFinished())
    node = node.add_child(ApplicationDataGenerator(
        bytearray(b"GET / HTTP/1.0\r\n\r\n")))
    node = node.add_child(ExpectApplicationData())
    node = node.add_child(AlertGenerator(AlertLevel.warning,
                                         AlertDescription.close_notify))
    node = node.add_child(ExpectAlert(AlertLevel.warning,
                                      AlertDescription.close_notify))
    node.next_sibling = ExpectClose()
    node.add_child(ExpectClose())

    conversations["sanity"] = conversation

    conversation = Connect(host, port, timeout=timeout)
    node = conversation
    ext = {ExtensionType.renegotiation_info: None}
    if ems:
        ext[ExtensionType.extended_master_secret] = AutoEmptyExtension()
    ciphers = [CipherSuite.TLS_DHE_RSA_WITH_AES_128_CBC_SHA,
               CipherSuite.TLS_DHE_RSA_WITH_AES_256_CBC_SHA,
               CipherSuite.TLS_DHE_RSA_WITH_AES_128_GCM_SHA256,
               CipherSuite.TLS_DHE_RSA_WITH_AES_128_CBC_SHA256]
    ext[ExtensionType.signature_algorithms] = \
        SignatureAlgorithmsExtension().create(RSA_SIG_ALL)
    ext[ExtensionType.signature_algorithms_cert] = \
        SignatureAlgorithmsCertExtension().create(RSA_SIG_ALL)
    node = node.add_child(ClientHelloGenerator(ciphers, extensions=ext))
    srv_ext = {ExtensionType.renegotiation_info:None}
    if ems:
        srv_ext[ExtensionType.extended_master_secret] = None
    node = node.add_child(ExpectServerHello(extensions=srv_ext))
    node = node.add_child(ExpectCertificate())
    node = node.add_child(ExpectServerKeyExchange(valid_params=valid_params))
    node = node.add_child(ExpectServerHelloDone())
    node = node.add_child(ClientKeyExchangeGenerator())
    node = node.add_child(ChangeCipherSpecGenerator())
    node = node.add_child(FinishedGenerator())
    node = node.add_child(ExpectChangeCipherSpec())
    node = node.add_child(ExpectFinished())
    node = node.add_child(ApplicationDataGenerator(
        bytearray(b"GET / HTTP/1.0\r\n\r\n")))
    node = node.add_child(ExpectApplicationData())
    node = node.add_child(AlertGenerator(AlertLevel.warning,
                                         AlertDescription.close_notify))
    node = node.add_child(ExpectAlert(AlertLevel.warning,
                                      AlertDescription.close_notify))
    node.next_sibling = ExpectClose()
    node.add_child(ExpectClose())

    conversations["FFDH parameters check"] = conversation

    good = 0
    bad = 0
    xfail = 0
    xpass = 0
    failed = []
    xpassed = []
    num_limit = num_limit or len(conversations)

    # make sure that sanity test is run first and last
    # to verify that server was running and kept running throughout
    sanity_tests = [('sanity', conversations['sanity'])]
    if run_only:
        if num_limit > len(run_only):
            num_limit = len(run_only)
        regular_tests = [(k, v) for k, v in conversations.items() if
                         k in run_only]
    else:
        regular_tests = [(k, v) for k, v in conversations.items() if
                         (k != 'sanity') and k not in run_exclude]
    sampled_tests = sample(regular_tests, min(num_limit, len(regular_tests)))
    ordered_tests = chain(sanity_tests, sampled_tests, sanity_tests)

    for c_name, c_test in ordered_tests:
        if run_only and c_name not in run_only or c_name in run_exclude:
            continue
        print("{} -->\n".format(c_name).upper())
        time.sleep(1)

        runner = Runner(c_test)

        res = True
        exception = None
        try:
            runner.run()
        except Exception as exp:
            exception = exp
            print("Error while processing")
            print(traceback.format_exc())
            res = False

        if c_name in expected_failures:
            if res:
                xpass += 1
                xpassed.append(c_name)
                print("XPASS-expected failure but test passed\n")
            else:
                if expected_failures[c_name] is not None and \
                        expected_failures[c_name] not in str(exception):
                    bad += 1
                    failed.append(c_name)
                    print("Expected error message: {0}\n"
                          .format(expected_failures[c_name]))
                else:
                    xfail += 1
                    print("OK-expected failure\n")
        else:
            if res:
                good += 1
                print("OK\n")
            else:
                bad += 1
                failed.append(c_name)
        
        print("=" * CHARACTERS_LENGTH, "\n")

    print("Test end")
    print(20 * '=')
    print("version: {0}".format(version))
    print(20 * '=', '\n')
    print("TOTAL: {0}".format(len(sampled_tests) + 2*len(sanity_tests)))
    print("SKIP: {0}".format(len(run_exclude.intersection(conversations.keys()))))
    print("PASS: {0}".format(good))
    print("XFAIL: {0}".format(xfail))
    print("FAIL: {0}".format(bad))
    print("XPASS: {0}".format(xpass))
    print(20 * '=')
    sort = sorted(xpassed, key=natural_sort_keys)
    if sort:
        print("XPASSED:\n\t{0}".format('\n\t'.join(repr(i) for i in sort)))
    sort = sorted(failed, key=natural_sort_keys)
    if sort:
        print("FAILED:\n\t{0}".format('\n\t'.join(repr(i) for i in sort)))

    if bad or xpass:
        sys.exit(1)

if __name__ == "__main__":
    main()
