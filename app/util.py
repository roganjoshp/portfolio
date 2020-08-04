def jsprit_to_readable_time(num):
    hours = str(int(float(num) / 60))
    mins = str(int(float(num) % 60))
    return str.zfill(hours, 2) + ':' + str.zfill(mins, 2)


def readable_to_jsprit(string):
    hours, mins = string.split(':')
    num_time = int(hours) * 60 + int(mins)
    return num_time


def chunk(l, n):
    return [l[i:i + n] for i in range(0, len(l), n)]