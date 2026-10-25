"""Aggre-SE (structural-mcp ``Batch``, Docu-SE) project XML of a 0711 / 0721 analysis (decision 49).

``project`` takes the 耐震設計条件 of the input and the values that follow from the NDU model, and finds the DB1 of
each Case among the JRSNAP results; ``writer`` writes the XML as Aggre-SE itself saves it, with WebPier's fixed
conditions. Writing the project is not a seismic performance check (CONTEXT.md 耐震照査の入力).
"""

from .project import Project, ProjectError, build_pile_project, build_project, databases, ndu_databases
from .writer import BATCH_VERSION, write_project

__all__ = ["BATCH_VERSION", "Project", "ProjectError", "build_pile_project", "build_project", "databases", "ndu_databases",
           "write_project"]
