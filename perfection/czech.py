#!/usr/bin/env python
"""
Use the Czech et al. method for generating minimal perfect hashes for strings.
"""

import random
import collections

# Hmm...
from . import forest
from . import utils


__all__ = ['hash_parameters', 'make_hash', 'make_dict']


_info_fields = ('t1', 't2', 'g', 'indices')
HashInfo = collections.namedtuple('HashInfo', _info_fields)


class CzechHashBuilder(object):
    """
    A helper class that (iteratively) stores all data needed to create a Czech
    hash.

    The entire hash generation algorithm occurs in  __init__.
    """

    def __init__(self, words, minimize=False):
        # Store the words as an immutable sequence.
        self.words = tuple(words)

        # TODO: Index minimization
        self.indices = range(len(words[0]))

        # Each of the following steps add fields to `self`:

        # Mapping step:
        #  - n, t1, t2, f1, f2, graph
        self.generate_acyclic_graph()
        # Assignment step:
        #  - g
        self.assign()

        # Now hash_info will return the appropriate object.

    @property
    def hash_info(self):
        """
        HashInfo tuple for the created hash.
        """
        return HashInfo(*(getattr(self, key) for key in _info_fields))

    @property
    def hash_function(self):
        """
        Returns the hash function proper. Ensures that `self` is not bound to
        the returned closure.
        """
        assert hasattr(self, 'f1') and hasattr(self, 'f2')

        # These are not just convenient aliases for the given
        # attributes; if `self` would creep into the returned closure,
        # that would ensure that a reference to this big, fat object
        # would be kept alive; hence, any hash function would carry
        # around all of the auxiliary state that was created during the
        # creation of the hash parameters.  Omitting `self` ensures this
        # object has a change to be garbage collected.
        f1, f2, g = self.f1, self.f2, self.g

        def czech_hash(word):
            v1 = f1(word)
            v2 = f2(word)
            return g[v1] + g[v2]

        return czech_hash


    # Algorithm steps.

    def generate_acyclic_graph(self):
        """
        Generates an acyclic graph for the given words.
        Returns graph, and a list of edge-word associations.
        """

        # Maximum length of each table, respectively.
        # Hardcoded n = cm, where c = 3
        # There might be a good way to choose an appropriate C,
        # but [1] suggests the average amount of iterations needed
        # to generate an acyclic graph is sqrt(3).
        self.n = 3 * len(self.words)

        max_tries = len(self.words) ** 2
        for trial in xrange(max_tries):
            try:
                self.generate_or_fail()
            except forest.InvariantError:
                continue
            else:
                self.trials_taken = trial + 1
                break

    def generate_random_table(self):
        """
        Generates random tables for given word lists.
        """
        table = range(0, self.n)
        random.shuffle(table)
        return table

    def generate_or_fail(self):
        """
        Attempts to generate a random acyclic graph, raising an
        InvariantError if unable to.
        """

        t1 = self.generate_random_table()
        t2 = self.generate_random_table()
        f1 = self.generate_func(t1)
        f2 = self.generate_func(t2)
        edges = [(f1(word), f2(word)) for word in self.words]

        # Try to generate that graph, mack!
        # Note that failure to generate the graph here should be caught
        # by the caller.
        graph = forest.ForestGraph(edges=edges)

        # Associate each edge with its corresponding word.
        associations = {}
        for num in xrange(len(self.words)):
            edge = edges[num]
            word = self.words[num]
            associations[graph.canonical_order(edge)] = (num, word)

        # Assign all of these to the object.
        for name in ('t1', 't2', 'f1', 'f2', 'graph', 'associations'):
            self.__dict__[name] = locals()[name]

    def generate_func(self, table):
        """
        Generates a random table based mini-hashing function.
        """

        # Ensure that `self` isn't suddenly in the closure...
        n = self.n

        def func(word):
            return sum(x * ord(c) for x, c in zip(table, word)) % n

        return func

    def assign(self):
        # Create an vector of empty assignments.
        self.g = [None] * (self.n + 1)

        # Assign all vertices.
        for vertex in self.graph.vertices:
            assert isinstance(vertex, int) and vertex <= self.n
            # This vertex has already been assigned.
            if self.g[vertex] is not None:
                continue

            self.g[vertex] = 0
            self.assign_vertex(vertex)

    def assign_vertex(self, vertex,):
        for neighbour in self.graph.neighbours(vertex):
            if self.g[neighbour] is not None:
                # This neighbour has already been assigned.
                continue

            # Get the associated edge number
            edge = self.graph.canonical_order((vertex, neighbour))
            num, _word = self.associations[edge]

            # Assign this vertex such that
            # h(word) == g(vertex) + g(neighbour)
            self.g[neighbour] = num - self.g[vertex]
            self.assign_vertex(neighbour)

# API functions  ##############################################################

def hash_parameters(words, minimize_indices=False):
    """
    Gives hash parameters for the given set of words.

    >>> info = hash_parameters('sun mon tue wed thu fri sat'.split())
    >>> len(info.t1)
    21
    >>> len(info.t2)
    21
    >>> len(info.g) # g values are 1-indexed...
    22
    """
    # Ensure that we have an indexable sequence.
    words = tuple(words)

    # Delegate to the hash builder.
    return CzechHashBuilder(words).hash_info


def make_hash(words, *args, **kwargs):
    """
    Creates an ordered, minimal perfect hash function for the given sequence
    of words.

    >>> hf = make_hash(['sun', 'mon', 'tue', 'wed', 'thu', 'fri', 'sat'])
    >>> hf('fri')
    5
    >>> hf('sun')
    0
    """

    # Use the hash builder proper, because HashInfo is assumed to not
    # have the precious f1, and f2 attributes.
    info = CzechHashBuilder(words, *args, **kwargs)

    return info.hash_function


def make_dict(name, words, *args, **kwargs):
    """
    make_dict(name, words, *args, **kwargs) -> mapping subclass

    Takes a sequence of words (or a pre-built Czech HashInfo) and returns a
    mapping subclass called `name` (used a dict) that employs the use of the
    minimal perfect hash.

    This mapping subclass has guaranteed O(1) worst-case lookups, additions,
    and deletions, however is slower than dict() in practice.

    >>> months = 'jan feb mar apr may jun jul aug sep oct nov dec'.split()
    >>> MyDict = make_dict('MyDict', months) 
    >>> d = MyDict(dec=21, feb=None, may='hello')
    >>> d['jul'] = False
    >>> d
    MyDict([('feb', None), ('may', 'hello'), ('jul', False), ('dec', 21)])
    >>> del d['may']
    >>> del d['apr']
    Traceback (most recent call last):
    ...
    KeyError: 'apr'
    >>> len(d)
    3
    """

    info = CzechHashBuilder(words, *args, **kwargs)

    # Create a docstring that at least describes where the class came from...
    doc = """
        Dictionary-like object that uses minimal perfect hashing, perserving
        original order. This class was generated by `%s.%s(%r, ...)`.
        """ % (__name__, make_dict.__name__, name)

    # Delegate to create_dict.
    return utils.create_dict_subclass(name, info.hash_function, info.words, doc)


def to_hash_info(unknown):
    if isinstance(unknown, HashInfo) or isinstance(unknown, CzechHashBuilder):
        # Unknown is a CzechHash.
        return unknown
    return HashInfo(unknown)

    # Alternative method:
    def _exception_based():
        try:
            (unknown.t1, unknown.t2, unknown.f1, unknown.f2, unknown.g)
        except AttributeError:
            return CreateCzechHash(unknown)
        try:
            for attr in ('t1', 't2', 'f1', 'f2', 'g'):
                iter(getattr(unknown, attr))
        except TypeError:
            return CreateCzechHash(unknown)

        return unknown



def do_example():
    import keyword
    words = keyword.kwlist

    hb = CzechHashBuilder(words)

    print '/*', hb.t1, hb.t2, hb.g, '*/'
    print hb.graph.to_dot(edge_labels={
        edge: '%d: %s' % assoc for edge, assoc in hb.associations.items()
    })


if __name__ == '__main__':
    do_example()
