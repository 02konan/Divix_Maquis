from flask_login import UserMixin


class User(UserMixin):
    def __init__(self, id, nom, email, id_role, nom_role):
        self.id = id
        self.nom = nom
        self.email = email
        self.id_role = id_role
        self.nom_role = nom_role

    @classmethod
    def depuis_ligne(cls, ligne):
        if not ligne:
            return None
        return cls(
            id=ligne["id"],
            nom=ligne["nom"],
            email=ligne["email"],
            id_role=ligne["id_role"],
            nom_role=ligne["nom_role"],
        )
