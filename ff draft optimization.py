import pandas as pd

qb_predictions = pd.read_csv('qb_predictions25.csv')
rb_predictions = pd.read_csv('rb_predictions25.csv')
te_predictions = pd.read_csv('te_predictions25.csv')
wr_predictions = pd.read_csv('wr_predictions25.csv')

qb_predictions.insert(5, "position", 'QB', True)
rb_predictions.insert(5, "position", 'RB', True)
te_predictions.insert(5, "position", 'TE', True)
wr_predictions.insert(5, "position", 'WR', True)

for i in range(200):
    
    position = input("Position that was picked: ")
    picked = input("Player that was just picked: ")
    
    if position == 'qb':
        if picked not in qb_predictions:
            print("Player has been picked, try again")
        qb_predictions = qb_predictions.drop(qb_predictions[qb_predictions['player'] == picked].index)
        
    elif position == 'rb':
        if picked not in rb_predictions:
            print("Player has been picked, try again")
        rb_predictions = rb_predictions.drop(rb_predictions[rb_predictions['player'] == picked].index)
        
    elif position == 'te': 
        if picked not in te_predictions:
            print("Player has been picked, try again")
        te_predictions = te_predictions.drop(te_predictions[te_predictions['player'] == picked].index)
        
    elif position == 'wr':
        if picked not in wr_predictions:
            print("Player has been picked, try again")
        wr_predictions = wr_predictions.drop(wr_predictions[wr_predictions['player'] == picked].index)
    else:
        break
        
        
    nextbestqb = qb_predictions.head(1)
    nextbestrb = rb_predictions.head(1)
    nextbestwr = wr_predictions.head(1)
    nextbestte = te_predictions.head(1)
    
    print()
    print("These are the next best picks:")
    print()
    print(nextbestqb.to_string(index=False, header = False))
    print(nextbestrb.to_string(index = False, header = False))
    print(nextbestwr.to_string(index = False, header = False))
    print(nextbestte.to_string(index = False, header = False))
    print()    
