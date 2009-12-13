#!/usr/bin/env python
# author: Jesse Shieh (jesse.shieh@gmail.com)
#
# Given a list of invitees and their corresponding blacklists,
# determine whether or not a cycle is possible and if so
# return a rondam cycle

import random
from google.appengine.ext import db

def randomize_list(l):
  list = [x for x in l] # copy
  length = len(list)
  for i in range(length):
    j = random.randrange(i, length)
    list[i], list[j] = list[j], list[i]
  return list

# class BlacklistPerson:
#     def __init__(self, name="", blacklist=[]):
#         self.name = name
#         self.blacklist = blacklist

#     def __str__(self):
#         return str(db.get(self.name))

#     def is_blacklisted(self, person_key):
#         """
#         Returns if person is blacklisted
#         """
#         if not self.blacklist:
#             return False
#         return person in self.blacklist

class BlacklistNode:
    def __init__(self, value=""):
        self.value = value # this will be a person key
        self.children = [] # list of nodes

    def __str__(self):
        str = "%s: [" % self.value
        for child in self.children:
            str += "%s," % child.value
        str += "]"
        return str

    def __eq__(self, node):
        return self.value == node.value

    def maybe_add_child(self, node):
        if node == self:
            return
        if node.value in db.get(self.value).blacklist:
            return
        self.children.append(node)

class NoCycleFoundError(Exception):
  def __init__(self, value):
    self.value = value
  def __str__(self):
    return repr(self.value)

class BlacklistGraph:
    def __init__(self, items=[]):
        if not items:
            self.nodes = []
            return

        self.nodes = [BlacklistNode(x) for x in items]
        self.create_eligible_edges()

    def __str__(self):
        str = ""
        for node in self.nodes:
            str += "%s\n" % node
        return str

    def create_eligible_edges(self):
        if not self.nodes:
            return

        for node in self.nodes:
            for potential_child in self.nodes:
                node.maybe_add_child(potential_child)

    def random_cycle(self):
        """
        Finds a random cycle that traveses every node in the graph.
        Raises exception if none is found.
        Cycle must have at least 2 nodes.
        """
        # corner cases
        if not self.nodes:
            raise NoCycleFoundError, "No cycle found"

        # choose a random node to start on
        start = self.nodes[random.randrange(0, len(self.nodes))]
        visited = [start]

        # converting back to BlacklistPersons before returning
        return [x.value for x in self.random_cycle_helper(visited)]

    def random_cycle_helper(self, visited):
        """
        Helper method that keeps visited node state.
        """
        current = visited[-1]

        # check termination case
        if len(visited) == len(self.nodes):
            # visited list contains every node.
            # just make sure the last one connects to the
            # first one
            if visited[0] in current.children:
                return visited

        # randomize children so that this is a random cycle
        children = randomize_list(current.children)
        for child in children:
            tmp = []
            tmp.extend(visited)
            tmp.append(child)

            # don't go there if already visited
            if child in visited:
                continue

            try:
                return self.random_cycle_helper(tmp)
            except NoCycleFoundError:
                # try next child
                continue

        # nothing found through all children, raise exception
        raise NoCycleFoundError, "No cycle found from %s to %s" % (
            visited[-1], visited[0])

def test(g):
    try:
        cycle = g.random_cycle()
        print "Graph:"
        print g
        print "Cycle:"
        for x in cycle: print x
        return "Cycle Found"
    except:
        return "No Cycle Found"

def main():
    g = BlacklistGraph([])
    assert(test(g) == "No Cycle Found")

    g = BlacklistGraph(None)
    assert(test(g) == "No Cycle Found")

    jesse = BlacklistPerson(name="Jesse")
    joy = BlacklistPerson(name="Joy")
    janice = BlacklistPerson(name="Janice")
    june = BlacklistPerson(name="June")
    sue = BlacklistPerson(name="Sue")

    g = BlacklistGraph([jesse, joy, janice, june, sue])
    assert(test(g) == "Cycle Found")

    # prohibitive blacklist
    june.blacklist = [joy, sue, jesse, janice]
    g = BlacklistGraph([jesse, joy, janice, june, sue])
    assert(test(g) == "No Cycle Found")
    june.blacklist = None

    # only one possible
    jesse.blacklist = [joy, june, sue]
    janice.blacklist = [jesse, june, sue]
    joy.blacklist = [janice, jesse, sue]
    june.blacklist = [joy, janice, jesse]
    sue.blacklist = [joy, june, janice]
    g = BlacklistGraph([jesse, joy, janice, june, sue])
    assert(test(g) == "Cycle Found")
    june.blacklist = None
    joy.blacklist = None
    sue.blacklist = None
    jesse.blacklist = None
    janice.blacklist = None

    # internal cycle
    jesse.blacklist = [joy, june, sue]
    janice.blacklist = [joy, june, sue]
    g = BlacklistGraph([jesse, joy, janice, june, sue])
    assert(test(g) == "No Cycle Found")
    jesse.blacklist = None
    janice.blacklist = None

    # one element graph
    g = BlacklistGraph([jesse])
    assert(test(g) == "No Cycle Found")

    # two element graph
    g = BlacklistGraph([jesse, janice])
    assert(test(g) == "Cycle Found")

    # duplicate node
    g = BlacklistGraph([jesse, jesse])
    assert(test(g) == "No Cycle Found")

    # duplicate node with others
    g = BlacklistGraph([jesse, jesse, janice])
    assert(test(g) == "No Cycle Found")

    # prohibitive blacklists
    jesse.blacklist = [june]
    janice.blacklist = [june]
    joy.blacklist = [june]
    sue.blacklist = [june]
    g = BlacklistGraph([jesse, joy, janice, june, sue])
    assert(test(g) == "No Cycle Found")
    jesse.blacklist = None
    janice.blacklist = None
    joy.blacklist = None
    sue.blacklist = None

if __name__ == "__main__":
    main()
