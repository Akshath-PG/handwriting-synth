import sys, os; sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src" if "legacy" not in __file__ else ".."))
import pickle, cv2, numpy as np
from config import D, U
P=pickle.load(open(D+'lib.pkl','rb')); L=P['lib']

def trim(a, thr=40):
    ys,xs=np.where(a>thr)
    pad=4
    y0,y1,x0,x1=max(ys.min()-pad,0),min(ys.max()+pad,a.shape[0]-1),max(xs.min()-pad,0),min(xs.max()+pad,a.shape[1]-1)
    return a[y0:y1+1,x0:x1+1], (ys.max()-ys.min()+1, xs.max()-xs.min()+1)

def cropfrac(ch, x0=0.0, x1=1.0, y0=0.0, y1=1.0):
    a=L[ch]['alpha']; H,W=a.shape
    sub=a[int(y0*H):int(y1*H), int(x0*W):int(x1*W)]
    sub,(h,w)=trim(sub)
    L[ch]['alpha']=sub; L[ch]['h']=float(h); L[ch]['w']=float(w); L[ch]['pad']=4.0

cropfrac('x', x0=0.42)
cropfrac('y', x0=0.52)
cropfrac('X', x0=0.52)
cropfrac('φ', x0=0.60)
cropfrac('w', y1=0.46)
a=L['≅']['alpha']; a[int(0.7*a.shape[0]):, int(0.8*a.shape[1]):]=0; L['≅']['alpha']=a
pickle.dump(P,open(D+'lib.pkl','wb'))
chs=['w','x','y','X','φ','≅']
canvas=np.full((130,len(chs)*130),255,np.uint8)
for i,c in enumerate(chs):
    a=L[c]['alpha']; s=min(110/a.shape[0],110/a.shape[1],1.5)
    t=cv2.resize(255-a,(int(a.shape[1]*s),int(a.shape[0]*s)))
    canvas[10:10+t.shape[0],i*130+5:i*130+5+t.shape[1]]=t
cv2.imwrite(D+'fix_check.png',canvas)
