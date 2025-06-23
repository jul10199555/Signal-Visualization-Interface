def check_int(entry: str):
    '''
    Check if given entry is of int data type. If entry is null, returns default
    '''
    return entry.isdigit() or entry == ""
    
def check_float(entry: str):
    '''
    Check if given entry is of float data type. If entry is null, returns default
    '''
    try:
        return float(entry)
    except:
        return 0
    
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