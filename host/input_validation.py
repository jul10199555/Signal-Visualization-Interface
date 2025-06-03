def check_int(entry: str, default):
    '''
    Check if given entry is of int data type. If entry is null, returns default
    '''
    if entry == "":
        return default
    elif entry.isdigit():
        return entry
    else:
        return None
    
def check_float(entry: str, default):
    '''
    Check if given entry is of float data type. If entry is null, returns default
    '''
    try:
        if entry == "":
            return default
        num = float(entry)
        if num > 0:
            return num
        else:
            return None
    except:
        return None
    
def check_lim(entry: str, default):
    '''
    Check if given entry matches 'a,b'. If entry is null, returns default
    '''
    try:
        if entry == "":
            return default
        pair = tuple(map(float, entry.split(',')))
        return pair
    except:
        return None