"""
Source governance package — runtime registry lookup and validation.

Modules
-------
registry
    Load and query ``data/sources/registry.yaml``.
validation
    Validate :class:`~src.schema.psdl.SourceRef` entries in a PSDL document
    against the registry's tier and allowed-use rules.
"""
