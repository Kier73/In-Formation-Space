"""Independent coverage and interface-translation checks for CIG-012.

The receiver must have admitted the old message already. Equality of a hash
alone is not an admission. Original-source tree audit precedes every traversal.
"""
from verify_adaptive_ground import verify_projection


def check_join_coverage(left,right,lb,rb,boundary):
    """Every shared or externally requested coordinate remains visible."""
    l,r=set(left[0]),set(right[0]);lb,rb,b=map(set,(lb,rb,boundary))
    return (not set(left[1])&set(right[1]) and
            lb<=l and rb<=r and b<=l|r and
            (l&r)|(b&l)<=lb and (l&r)|(b&r)<=rb)


def check_transfer(old_coverage,new_coverage,old,new):
    """Same source region AND domain; exact same interface or marginal only."""
    if (set(old_coverage[0])!=set(new_coverage[0]) or
        set(old_coverage[1])!=set(new_coverage[1])):return False
    if old['boundary']==new['boundary']:
        return old['counts']==new['counts']
    return verify_projection(old,new)
