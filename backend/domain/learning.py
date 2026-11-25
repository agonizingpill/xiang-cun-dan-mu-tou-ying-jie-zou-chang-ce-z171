import numpy as np
from sklearn.cluster import AgglomerativeClustering

def dtw(a,b):
    dist=np.full((len(a)+1,len(b)+1),np.inf)
    dist[0,0]=0
    for i,x in enumerate(a,1):
        for j,y in enumerate(b,1):
            dist[i,j]=abs(x-y)+min(dist[i-1,j],dist[i,j-1],dist[i-1,j-1])
    return float(dist[-1,-1]/(len(a)+len(b)))

def calculate(data):
    rows=data['references']+[data['track']]
    count=len(rows)
    distances=np.zeros((count,count))
    for i in range(count):
        for j in range(i):
            distances[i,j]=distances[j,i]=dtw(rows[i]['timings'],rows[j]['timings'])
    labels=AgglomerativeClustering(n_clusters=3,metric='precomputed',linkage='average').fit_predict(distances)
    members=[i for i in range(count-1) if labels[i]==labels[-1]]
    if not members:
        raise ValueError('当前轨迹独立成簇，需追加场测')
    representative=min(members,key=lambda i:sum(distances[i,j] for j in members))
    return {'representative':rows[representative]['code'],'distance':round(distances[-1,representative],4),
            'members':[rows[i]['code'] for i in members],'reference_count':count-1}
