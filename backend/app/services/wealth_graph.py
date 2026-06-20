"""
Neo4j Wealth Graph Service — Financial knowledge graph for multi-hop reasoning.

Node types:
  - User            (name, monthly_income, risk_profile)
  - Goal            (name, type, target, current, priority)
  - Asset           (name, type, value)
  - Liability       (name, type, amount, interest_rate)
  - IncomeSource    (name, monthly_amount)
  - ExpenseCategory (name, monthly_total)

Relationships:
  - (User)-[:HAS_GOAL]->(Goal)
  - (User)-[:OWNS]->(Asset)
  - (User)-[:OWES]->(Liability)
  - (User)-[:EARNS_FROM]->(IncomeSource)
  - (User)-[:SPENDS_ON]->(ExpenseCategory)
  - (ExpenseCategory)-[:DELAYS]->(Goal)  [computed: high spending delays goals]
  - (Liability)-[:BLOCKS]->(Goal)         [computed: debt blocks goals]
"""
import logging
from collections import defaultdict
from sqlalchemy.orm import Session
from .. import models
from ..database import get_neo4j

logger = logging.getLogger("finmate.wealth_graph")


def sync_graph(db: Session, user_id: int):
    """Sync PostgreSQL data into Neo4j wealth graph."""
    driver = get_neo4j()
    if not driver:
        logger.info("Neo4j not available — skipping graph sync.")
        return
    
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        return
    
    txns = db.query(models.Transaction).filter(models.Transaction.user_id == user_id).all()
    goals = db.query(models.Goal).filter(models.Goal.user_id == user_id).all()
    assets = db.query(models.Asset).filter(models.Asset.user_id == user_id).all()
    liabilities = db.query(models.Liability).filter(models.Liability.user_id == user_id).all()
    
    # Compute aggregates
    income_sources = defaultdict(float)
    expense_categories = defaultdict(float)
    for t in txns:
        if t.amount > 0:
            source_name = t.merchant or t.category
            income_sources[source_name] += t.amount
        else:
            expense_categories[t.category] += -t.amount
    
    with driver.session() as session:
        # Clear existing data for this user
        session.run("MATCH (u:User {user_id: $uid})-[r]-() DELETE r", uid=user_id)
        session.run("MATCH (u:User {user_id: $uid}) DETACH DELETE u", uid=user_id)
        
        # Create User node
        session.run(
            """
            CREATE (u:User {
                user_id: $uid, name: $name, 
                monthly_income: $income, risk_profile: $risk
            })
            """,
            uid=user_id, name=user.name,
            income=user.monthly_income, risk=user.risk_profile,
        )
        
        # Create Goal nodes
        for g in goals:
            session.run(
                """
                MATCH (u:User {user_id: $uid})
                CREATE (g:Goal {
                    goal_id: $gid, name: $name, goal_type: $gtype,
                    target_amount: $target, current_amount: $current,
                    monthly_contribution: $contrib, priority: $priority
                })
                CREATE (u)-[:HAS_GOAL]->(g)
                """,
                uid=user_id, gid=g.id, name=g.name, gtype=g.goal_type,
                target=g.target_amount, current=g.current_amount,
                contrib=g.monthly_contribution, priority=g.priority,
            )
        
        # Create Asset nodes
        for a in assets:
            session.run(
                """
                MATCH (u:User {user_id: $uid})
                CREATE (a:Asset {asset_id: $aid, name: $name, asset_type: $atype, value: $val})
                CREATE (u)-[:OWNS]->(a)
                """,
                uid=user_id, aid=a.id, name=a.name, atype=a.asset_type, val=a.value,
            )
        
        # Create Liability nodes
        for l in liabilities:
            session.run(
                """
                MATCH (u:User {user_id: $uid})
                CREATE (l:Liability {
                    liability_id: $lid, name: $name, liability_type: $ltype,
                    amount: $amt, interest_rate: $rate, monthly_payment: $payment
                })
                CREATE (u)-[:OWES]->(l)
                """,
                uid=user_id, lid=l.id, name=l.name, ltype=l.liability_type,
                amt=l.amount, rate=l.interest_rate, payment=l.monthly_payment,
            )
        
        # Create IncomeSource nodes
        for source, total in income_sources.items():
            session.run(
                """
                MATCH (u:User {user_id: $uid})
                CREATE (s:IncomeSource {name: $name, total_amount: $total})
                CREATE (u)-[:EARNS_FROM]->(s)
                """,
                uid=user_id, name=source, total=total,
            )
        
        # Create ExpenseCategory nodes + DELAYS relationships
        top_goal = goals[0] if goals else None
        for category, total in expense_categories.items():
            session.run(
                """
                MATCH (u:User {user_id: $uid})
                CREATE (e:ExpenseCategory {name: $name, total_amount: $total})
                CREATE (u)-[:SPENDS_ON]->(e)
                """,
                uid=user_id, name=category, total=total,
            )
            
            # Link high-spend categories to goals they delay
            if top_goal and total > user.monthly_income * 0.1:
                session.run(
                    """
                    MATCH (e:ExpenseCategory {name: $cat})
                    MATCH (g:Goal {goal_id: $gid})
                    CREATE (e)-[:DELAYS {monthly_impact: $impact}]->(g)
                    """,
                    cat=category, gid=top_goal.id, impact=round(total * 0.2, 2),
                )
        
        # Link liabilities that BLOCK goals
        for l in liabilities:
            if top_goal and l.monthly_payment > 0:
                session.run(
                    """
                    MATCH (li:Liability {liability_id: $lid})
                    MATCH (g:Goal {goal_id: $gid})
                    CREATE (li)-[:BLOCKS {monthly_drain: $drain}]->(g)
                    """,
                    lid=l.id, gid=top_goal.id, drain=l.monthly_payment,
                )
    
    logger.info("Synced wealth graph for user %d: %d goals, %d assets, %d liabilities, %d expense categories",
                user_id, len(goals), len(assets), len(liabilities), len(expense_categories))


def get_graph_context(user_id: int) -> dict:
    """
    Extract graph-based insights for the AI CFO agent.
    Returns structured context about relationships between financial entities.
    """
    driver = get_neo4j()
    if not driver:
        return {"available": False}
    
    try:
        with driver.session() as session:
            # What's delaying goals?
            delays = session.run(
                """
                MATCH (e:ExpenseCategory)-[d:DELAYS]->(g:Goal)
                MATCH (:User {user_id: $uid})-[:SPENDS_ON]->(e)
                RETURN e.name AS category, g.name AS goal, d.monthly_impact AS impact
                ORDER BY d.monthly_impact DESC LIMIT 5
                """,
                uid=user_id,
            ).data()
            
            # What's blocking goals?
            blocks = session.run(
                """
                MATCH (l:Liability)-[b:BLOCKS]->(g:Goal)
                MATCH (:User {user_id: $uid})-[:OWES]->(l)
                RETURN l.name AS liability, g.name AS goal, b.monthly_drain AS drain
                ORDER BY b.monthly_drain DESC LIMIT 5
                """,
                uid=user_id,
            ).data()
            
            # Income sources
            income = session.run(
                """
                MATCH (:User {user_id: $uid})-[:EARNS_FROM]->(s:IncomeSource)
                RETURN s.name AS source, s.total_amount AS total
                ORDER BY s.total_amount DESC LIMIT 5
                """,
                uid=user_id,
            ).data()
            
            # Asset composition
            asset_summary = session.run(
                """
                MATCH (:User {user_id: $uid})-[:OWNS]->(a:Asset)
                RETURN a.asset_type AS type, sum(a.value) AS total
                ORDER BY total DESC
                """,
                uid=user_id,
            ).data()
            
            return {
                "available": True,
                "goal_delays": delays,
                "goal_blocks": blocks,
                "income_sources": income,
                "asset_composition": asset_summary,
            }
    except Exception as e:
        logger.warning("Failed to query wealth graph: %s", e)
        return {"available": False}


def get_full_graph(user_id: int) -> dict:
    """Get the complete graph for visualization on the frontend."""
    driver = get_neo4j()
    if not driver:
        return {"nodes": [], "edges": []}
    
    try:
        with driver.session() as session:
            # Get all nodes
            result = session.run(
                """
                MATCH (u:User {user_id: $uid})
                OPTIONAL MATCH (u)-[r]->(n)
                RETURN u, r, n, labels(n) AS node_labels, type(r) AS rel_type
                """,
                uid=user_id,
            )
            
            nodes = []
            edges = []
            seen_nodes = set()
            
            for record in result:
                # User node
                u = record["u"]
                if "user" not in seen_nodes:
                    nodes.append({"id": "user", "label": u["name"], "type": "User"})
                    seen_nodes.add("user")
                
                # Connected node
                n = record["n"]
                if n:
                    labels = record["node_labels"]
                    node_type = labels[0] if labels else "Unknown"
                    node_id = f"{node_type}_{dict(n).get('name', 'unknown')}"
                    
                    if node_id not in seen_nodes:
                        node_data = {"id": node_id, "label": n.get("name", "Unknown"), "type": node_type}
                        if "value" in n:
                            node_data["value"] = n["value"]
                        if "amount" in n:
                            node_data["value"] = n["amount"]
                        if "total_amount" in n:
                            node_data["value"] = n["total_amount"]
                        nodes.append(node_data)
                        seen_nodes.add(node_id)
                    
                    # Edge
                    rel_type = record["rel_type"]
                    if rel_type:
                        edges.append({"from": "user", "to": node_id, "label": rel_type})
            
            return {"nodes": nodes, "edges": edges}
    except Exception as e:
        logger.warning("Failed to get full graph: %s", e)
        return {"nodes": [], "edges": []}
