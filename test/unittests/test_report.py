import sys
import os
import shutil
from nose.tools import eq_, ok_

from hb_report.utillib import which, ts_to_dt, sub_string, random_string,\
                              head, create_tempfile, tail, grep,\
                              get_stamp_rfc5424, get_stamp_syslog,\
                              find_getstampproc_raw, find_getstampproc,\
                              get_ts, is_our_log, find_first_ts, arch_logs,\
                              add_tempfiles, make_temp_dir,\
                              find_decompressor, find_files, filter_lines,\
                              findln_by_time, get_conf_var, is_conf_set,\
                              line_time, get_command_info, Tempfile
from hb_report import constants
import crmsh.utils


######## test data begin ########
pacemaker_log = "pacemaker.log"
pacemaker_unicode_log = "pacemaker_unicode.log"
evil_unicode_log = "evil_unicode.txt"
invalid_utf8 = b'Apr 03 11:01:18 [13042] \xe5abc\nApr 03 11:01:18 [13042] test\xe5'

time_before = crmsh.utils.parse_to_timestamp("2019/04/03 11:01:00")
time_after = crmsh.utils.parse_to_timestamp("2019/04/03 14:00:00")
time_between = crmsh.utils.parse_to_timestamp("2019/04/03 12:03:31")
first_time = crmsh.utils.parse_to_timestamp("2019/04/03 11:01:18")

line5424_1 = r"2017-01-26T11:04:19.562885+08:00 12sp2-4 kernel: [    0.000000]"
line5424_2 = r"2017-07-10T01:33:54.993374+08:00 12sp2-1 pengine[2020]:   notice: Calculated transition 221"

linesyslog_1 = r"May 17 15:52:40 [13042] 12sp2-4 pacemakerd:   notice: main:"
linesyslog_2 = r"Jul 09 18:33:54 [2020] 12sp2-1    pengine:     info: determine_online_status:   Node 12sp2-1 is online"

log_file_string = """logging {
        fileline:       off
        to_stderr:      no
        to_logfile:     no
        logfile:        /var/log/cluster/corosync.log
        to_syslog:      yes
        debug:          off
        timestamp:      on
        logger_subsys {
                subsys: QUORUM
                debug:  off
        }
}"""

sample_string1 = """some aaa
some bbbb
some cccc
some dddd"""
######## test data end ########


def test_arch_logs():
    # test blank file
    temp_file = create_tempfile()
    ok_(not arch_logs(temp_file, time_before, time_between))

    # from_time > last_time
    ok_(not arch_logs(pacemaker_log, time_after, time_between))
    # from_time >= first_time
    eq_(arch_logs(pacemaker_log, time_before, time_between)[0], pacemaker_log)
    # to_time == 0
    eq_(arch_logs(pacemaker_log, time_before, 0)[0], pacemaker_log)
    # to_time >= first_time
    eq_(arch_logs(pacemaker_log, time_before, first_time)[0], pacemaker_log)

    os.remove(temp_file)


def test_Tempfile():
    t = Tempfile()

    tmpdir = make_temp_dir()
    t.add(tmpdir)

    tmpfile = create_tempfile()
    t.add(tmpfile)

    ok_(os.path.isdir(tmpdir))
    ok_(os.path.isfile(tmpfile))
    ok_(os.path.isfile(t.file))

    t.drop()

    ok_(not os.path.isdir(tmpdir))
    ok_(not os.path.isfile(tmpfile))
    ok_(not os.path.isfile(t.file))


def test_filter_lines():
    begin_line = findln_by_time(pacemaker_log, time_before)
    end_line = findln_by_time(pacemaker_log, time_between)

    out1 = filter_lines(pacemaker_log, begin_line)
    out2 = filter_lines(pacemaker_log, begin_line, end_line)

    eq_(len(out1.split('\n')), 924)
    eq_(len(out2.split('\n')), 804)


def test_filter_lines_unicode():
    with open(evil_unicode_log, 'wb') as f:
        f.write(invalid_utf8)
    out1 = filter_lines(evil_unicode_log, 1, 3)
    eq_(len(out1.split('\n')), 2)
    os.remove(evil_unicode_log)

    out2 = filter_lines(pacemaker_unicode_log, 1, 30)
    eq_(len(out2.split('\n')), 31)


def test_find_decompressor():
    log_file = "testfile"
    eq_(find_decompressor(log_file), "cat")
    log_file = "log.bz2"
    eq_(find_decompressor(log_file), "bzip2 -dc")
    log_file = "log.gz"
    eq_(find_decompressor(log_file), "gzip -dc")
    log_file = "log.tar.xz"
    eq_(find_decompressor(log_file), "xz -dc")

    log_file = create_tempfile()
    with open(log_file, 'w') as f:
        f.write("test")
    eq_(find_decompressor(log_file), "cat")
    os.remove(log_file)


def test_find_first_ts():
    with open(pacemaker_log, 'r') as f:
        res = find_first_ts(f.read().split('\n'))
        eq_(ts_to_dt(res).strftime("%Y/%m/%d %H:%M:%S"), "2019/04/03 11:01:18")


def test_find_files():
    ok_(not find_files("test", "testtime", time_after))
    ok_(not find_files("test", 0, time_after))

    dirs = make_temp_dir()
    tmpfile1 = create_tempfile(time_between)
    tmpfile2 = create_tempfile(time_after)
    shutil.copy2(tmpfile1, dirs)
    shutil.copy2(tmpfile2, dirs)

    t = Tempfile()
    t.add(dirs)
    t.add(tmpfile1)
    t.add(tmpfile2)

    eq_(sorted(find_files(dirs, time_before, 0)), sorted([os.path.join(dirs, os.path.basename(tmpfile1)), os.path.join(dirs, os.path.basename(tmpfile2))]))
    eq_(find_files(dirs, time_before, time_between), [os.path.join(dirs, os.path.basename(tmpfile1))])

    t.drop()


def test_find_getstampproc():
    temp_file = create_tempfile()

    in_string1 = """abcd
efg"""
    with open(temp_file, 'w') as f:
        f.write(in_string1)
    ok_(not find_getstampproc(temp_file))

    in_string2 = """%s
%s""" % (line5424_1, line5424_2)
    with open(temp_file, 'w') as f:
        f.write(in_string2)
    eq_(find_getstampproc(temp_file), "rfc5424")

    in_string3 = """%s
%s""" % (linesyslog_1, linesyslog_2)
    with open(temp_file, 'w') as f:
        f.write(in_string3)
    eq_(find_getstampproc(temp_file), "syslog")

    os.remove(temp_file)


def test_find_getstampproc_unicode():
    eq_(find_getstampproc(pacemaker_unicode_log), "syslog")

    with open(evil_unicode_log, 'wb') as f:
        f.write(invalid_utf8)
    eq_(find_getstampproc(evil_unicode_log), "syslog")
    os.remove(evil_unicode_log)


def test_find_getstampproc_raw():
    eq_(find_getstampproc_raw(line5424_1), "rfc5424")
    eq_(find_getstampproc_raw(line5424_2), "rfc5424")
    eq_(find_getstampproc_raw(linesyslog_1), "syslog")
    eq_(find_getstampproc_raw(linesyslog_2), "syslog")


def test_findln_by_time():
    # time before log happen
    eq_(findln_by_time(pacemaker_log, time_before), 1)
    # time after log happen
    eq_(findln_by_time(pacemaker_log, time_after), 923)
    # time between log happen
    eq_(findln_by_time(pacemaker_log, time_between), 803)


def test_findln_by_time():
    eq_(findln_by_time(pacemaker_unicode_log, time_before), 1)

    with open(evil_unicode_log, 'wb') as f:
        f.write(invalid_utf8)
    eq_(findln_by_time(evil_unicode_log, time_before), 1)
    os.remove(evil_unicode_log)


def test_get_stamp_rfc5424():
    ok_(get_stamp_rfc5424(line5424_1))
    ok_(get_stamp_rfc5424(line5424_2))


def test_get_stamp_syslog():
    ok_(get_stamp_syslog(linesyslog_1))
    ok_(get_stamp_syslog(linesyslog_2))


def test_get_ts():
    eq_(ts_to_dt(get_ts(line5424_1)).strftime("%Y/%m/%d %H:%M"), "2017/01/26 03:04")
    eq_(ts_to_dt(get_ts(linesyslog_1)).strftime("%m/%d %H:%M:%S"), "05/17 15:52:40")


def test_grep():
    res = grep("^Name", incmd="rpm -qi bash")[0]
    _, out = get_command_info("rpm -qi bash|grep \"^Name\"")
    eq_(res, out.strip("\n"))

    in_string = """aaaa
bbbb
"""
    temp_file = create_tempfile()
    with open(temp_file, 'w') as f:
        f.write(in_string)
    res = grep("aaaa", infile=temp_file, flag='v')[0]
    _, out = get_command_info("grep -v aaaa %s"%temp_file)
    os.remove(temp_file)
    eq_(res, out.strip("\n"))


def test_grep_unicode():
    with open(evil_unicode_log, 'wb') as f:
        f.write(invalid_utf8)
    res = grep("11:01", infile=evil_unicode_log)[0]
    os.remove(evil_unicode_log)
    eq_(res, 'Apr 03 11:01:18 [13042] \ufffdabc')

    res = grep("test_unicode", infile=pacemaker_unicode_log)[0]
    eq_(res, 'Apr 03 13:37:23 15sp1-1 pacemaker-controld  [1948] (handle_ping)        notice: \\xfc\\xa1\\xa1\\xa1\\xa1\\xa1 test_unicode')


def test_head():
    temp_file = create_tempfile()
    with open(temp_file, 'w') as f:
        f.write(sample_string1)
    _, out = get_command_info("cat %s|head -3" % temp_file)
    with open(temp_file, 'r') as f:
        data = f.read()
    res = head(3, data)

    os.remove(temp_file)
    eq_(out.rstrip('\n'), '\n'.join(res))


def test_is_our_log():
    # empty log
    temp_file = create_tempfile()
    eq_(is_our_log(temp_file, time_before, time_between), 0)

    # from_time > last_time
    eq_(is_our_log(pacemaker_log, time_after, time_between), 2)
    # from_time >= first_time
    eq_(is_our_log(pacemaker_log, time_between, time_after), 3)
    # to_time == 0
    eq_(is_our_log(pacemaker_log, time_before, 0), 1)
    # to_time >= first_time
    eq_(is_our_log(pacemaker_log, time_before, first_time), 1)

    os.remove(temp_file)


def test_is_our_log_unicode():
    eq_(is_our_log(pacemaker_unicode_log, time_before, 0), 1)

    with open(evil_unicode_log, 'wb') as f:
        f.write(invalid_utf8)
    eq_(is_our_log(evil_unicode_log, time_before, 0), 1)
    os.remove(evil_unicode_log)


def test_line_time():
    eq_(ts_to_dt(line_time(pacemaker_log, 2)).strftime("%Y/%m/%d %H:%M:%S"), "2019/04/03 11:01:18")
    eq_(ts_to_dt(line_time(pacemaker_log, 195)).strftime("%Y/%m/%d %H:%M:%S"), "2019/04/03 11:01:40")


def test_line_time_unicode():
    eq_(ts_to_dt(line_time(pacemaker_unicode_log, 3)).strftime("%Y/%m/%d %H:%M:%S"), "2019/04/03 11:01:18")
    with open(evil_unicode_log, 'wb') as f:
        f.write(invalid_utf8)
    eq_(ts_to_dt(line_time(evil_unicode_log, 1)).strftime("%Y/%m/%d %H:%M:%S"), "2019/04/03 11:01:18")
    os.remove(evil_unicode_log)


def test_random_string():
    eq_(len(random_string(8)), 8)


def test_sub_string():
    in_string = """
some text some text
I like name="OSS" value="redhat" target="mememe".
I like name="password" value="123456" some="more".
some number some number
"""

    out_string = """
some text some text
I like name="OSS" value="******" target="mememe".
I like name="password" value="******" some="more".
some number some number
"""
    pattern = "passw.* OSS"
    eq_(sub_string(in_string, pattern), out_string)


def test_tail():
    temp_file = create_tempfile()
    with open(temp_file, 'w') as f:
        f.write(sample_string1)
    _, out = get_command_info("cat %s|tail -3" % temp_file)
    with open(temp_file, 'r') as f:
        data = f.read()
    res = tail(3, data)

    os.remove(temp_file)
    eq_(out.rstrip('\n'), '\n'.join(res))


def test_ts_to_dt():
    ts1 = crmsh.utils.parse_to_timestamp("2pm")
    ts2 = crmsh.utils.parse_to_timestamp("2007/9/5 12:30")
    ts3 = crmsh.utils.parse_to_timestamp("1:00")
    ts4 = crmsh.utils.parse_to_timestamp("09-Sep-15 2:00")
    ts5 = crmsh.utils.parse_to_timestamp("2017-06-01T14:27:08.412531+08:00")

    eq_(ts_to_dt(ts1).strftime("%-I%P"), "2pm")
    eq_(ts_to_dt(ts2).strftime("%Y/%-m/%-d %H:%M"), "2007/9/5 12:30")
    eq_(ts_to_dt(ts3).strftime("%-H:%M"), "1:00")
    eq_(ts_to_dt(ts4).strftime("%d-%b-%y %-H:%M"), "09-Sep-15 2:00")
    eq_(ts_to_dt(ts5).strftime("%Y/%m/%d %H:%M:%S"), "2017/06/01 06:27:08")


def test_which():
    ok_(which("ls"))
    ok_(not which("llll"))
