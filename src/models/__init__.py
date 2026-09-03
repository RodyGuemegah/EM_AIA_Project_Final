from src.models.dataset import load_bronze, split_par_moteur
df = load_bronze()
print(len(df), df.engine_id.nunique())      # attendu : 20631 100

tr, te = split_par_moteur(df)
print(tr.engine_id.nunique(), te.engine_id.nunique())   # attendu : 80 20
print(set(tr.engine_id) & set(te.engine_id))            # attendu : set() — vide