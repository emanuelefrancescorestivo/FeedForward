"""
graph/feedforward.py
--------------------
The graph data structure. Per the review this must be hand-written (no
NetworkX as the backing store). Your proposal (§6) already commits to a
weighted adjacency list:

    adj: dict[str, list[tuple[str, float]]]

THE SEED QUESTION you are answering here: given foods and nutrients, how do
you store who-contains-what in a plain dict, and what does it COST to answer
"which foods contain iron?"  Understand that cost before writing a line.
"""


class FeedForwardGraph:
    def __init__(self):
    # il grafo è un dizionario:
    # chiave = nome del nodo (stringa)
    # valore = lista di (vicino, peso)
        self.adj : dict[str, list[tuple[str, float]]] = {}
    
    def add_node(self, node_id, node_type=None):
    # se il nodo non esiste ancora, crealo con lista vuota
    # se esiste già, non fare nulla (non sovrascrivere!)
        if node_id not in self.adj:
            self.adj[node_id] = []

    def add_edge(self, source, destination, weight):
        # src = sorgente (da dove parte l'arco)
        # dst = destinazione (dove arriva l'arco)
        # weight = peso dell'arco

        # se la sorgente non esiste, creala automaticamente
        if source not in self.adj:
            self.add_node(source)

        # se la destinazione non esiste, creala automaticamente
        # (serve per poter fare neighbors("omega_3") anche se
        #  omega_3 è stato aggiunto solo come destinazione)
        if destination not in self.adj:
            self.add_node(destination)

        # aggiungi l'arco: nella lista di src, metti la coppia (dst, peso)
        self.adj[source].append((destination, weight))


    def neighbours(self, node_id):
        # restituisce la lista di (vicino, peso) che partono da node_id
        # .get(chiave, default) evita KeyError se il nodo non esiste
        return self.adj.get(node_id, [])
