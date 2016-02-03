#!/usr/bin/env python
# coding: utf8
""" Generate rankings for a country and a year """
import subprocess
import json
from collections import defaultdict

YEAR = "2015"
COUNTRY = "France"
DATA_DIR = "data/"
BUILD_DIR = "build/"
# Best N competitions to consider
BEST_OF = 6
COMPETITIONS_FILE = DATA_DIR + "WCA_export_Competitions.tsv"
RESULTS_FILE = DATA_DIR + "WCA_export_Results.tsv"
EVENTS = ["333", "444", "222", "333oh", "333bf", "pyram"]

SCORE_TABLE = dict()

class CompetitionRank(object):
    """ The competition rank enum. """
    (MINOR, INTERMEDIATE, MAJOR) = range(3)


class Competition(object):
    """ Object representing a competition """
    # Static set of competitors per event
    competitors_per_event = defaultdict(set)

    def __init__(self, cid, month, day):
        """ Init from competition's id, day/month to be able to sort """
        self.cid = cid
        self.month = int(month)
        self.day = int(day)
        # Dictionary of results, event -> list of Result
        self.results = defaultdict(list)

    def add_result(self, event, res, single, average):
        """ Add a result to an event of the competition """
        try:
            # Try to update existing result
            # (in case of multiple round, final round should override previous round)
            index = self.results[event].index(res)
            self.results[event][index] = res
        except ValueError:
            # Result was not found, check if it's not DNF and insert it
            # (we don't ignore subsequent DNF, so that one DNFing in final still has point)
            if int(single) <= 0 and int(average) <= 0:
                return
            self.results[event].append(res)
            # Add competitor to the set of competitor per event (the set guarantees unicity)
            Competition.competitors_per_event[event].add(res.competitor)

    def get_competitor_result(self, competitor, event):
        """ Get the competitor's result for a given event """
        if event not in self.results.keys():
            return None
        try:
            return next(x for x in self.results[event] if x.competitor == competitor)
        except StopIteration:
            return None


    @property
    def rank(self):
        # Determine the rank of the competition based on the number of 3x3 competitors
        ncompetitors33 = len(self.results["333"])
        if ncompetitors33 >= 50:
            return CompetitionRank.MAJOR
        elif ncompetitors33 >= 20:
            return CompetitionRank.INTERMEDIATE
        else:
            return CompetitionRank.MINOR

    def __lt__(self, other):
        # Sort on month then day (we assume it's only for a given year)
        if self.month == other.month:
            return self.day < other.day
        else:
            return self.month < other.month

    def __eq__(self, other):
        return self.cid == other.cid

    def __ne__(self, other):
        return self.cid != other.cid

    def __hash__(self):
        return hash(self.cid)



class Result(object):
    def __init__(self, competitor, pos, event_round):
        self.competitor = competitor
        self.pos = int(pos)
        self.event_round = event_round

    def __lt__(self, other):
        return self.pos < other.pos

    def __eq__(self, other):
        return self.competitor == other.competitor

    def __ne__(self, other):
        return self.competitor != other.competitor

class Competitor(object):
    def __init__(self, wca_id, name):
        self.wca_id = wca_id
        self.competitions = set()
        self.name = name
        # Fast sort
        self.total_score_indexes = dict()

    def add_competition(self, comp):
        """ Add a competition to this competitor's set of comp"""
        # Same here, the set guarantees unicity
        self.competitions.add(comp)

    def to_json(self):
        """ Convert a competitor to json. """
        # Actually here it's not an exact serialization of the competitor
        # We want to compute the following association :
        # WCA_id -> { name,  event -> { total_score, event_pos,
        #                               comp_list -> [comp_result, ...], ... }
        res_dict = dict()
        for event in EVENTS:
            event_dict = self._get_result_dict_for_event(event)
            if len(event_dict['comp_list']) > 0:
                res_dict[event] = event_dict
        res_dict['name'] = self.name
        return res_dict

    def _get_result_dict_for_event(self, event):
        """ Generate the dict for a given event """
        res_dict = dict()
        res_list = []
        # Loop through our competitions
        for comp in sorted(self.competitions):
            comp_res = comp.get_competitor_result(self, event)
            comp_res_dict = dict()
            if comp_res is None:
                # We don't have result for this even in this competition...
                continue
            # Add this competition result to the dict,
            # and get the score matching our position
            comp_res_dict['comp_id'] = comp.cid
            # If we don't find a score, default to 1 (happens for pos >= 50)
            comp_res_dict['score'] = SCORE_TABLE[str(comp.rank)].get(str(comp_res.pos), 1)
            comp_res_dict['pos'] = comp_res.pos
            comp_res_dict['counting'] = True
            res_list.append(comp_res_dict)

        # Sort our results based on score to take only the BEST_OF first competitions
        res_list.sort(key=lambda x: x['score'], reverse=True)
        index = 0
        total = 0
        # Compute total score
        for res in res_list:
            if index < BEST_OF:
                total += res['score']
            else:
                # This is just to ease the work of the GUI
                res['counting'] = False
            index += 1
        res_dict['total_score'] = total
        res_dict['comp_list'] = res_list
        self.total_score_indexes[event] = total
        return res_dict


    def __eq__(self, other):
        return self.wca_id == other.wca_id

    def __hash__(self):
        return hash(self.wca_id)



class RankingGenerator(object):
    def __init__(self, country, year):
        # Competitions in the tournament
        self.competitions = []
        # Competitors having competed in one of these competitions
        self.competitors = dict()
        self.country = country
        self.year = year

    def to_json(self):
        """ Create the json representation of the rankings """
        # Here we want a root dictionary with two entries :
        # - 'competitors' indexed on wca_id with all the competitors scores
        # - 'events' indexed on event_id with the sorted list of wca_id
        ranking_dict = dict()
        ranking_dict['competitors'] = dict()
        ranking_dict['events'] = dict()
        for competitor in self.competitors.itervalues():
            ranking_dict['competitors'][competitor.wca_id] = competitor.to_json()


        for event in EVENTS:
            ranking_dict['events'][event] = list()
            index = 0
            # Output sorted competitors ranking for this event
            for comp in sorted(Competition.competitors_per_event[event],
                               key=lambda x: x.total_score_indexes[event],
                               reverse=True):
                index += 1
                # FIXME this is kinda ugly to do this here, but I couldn't
                # figure out something else
                ranking_dict['competitors'][comp.wca_id][event]['event_pos'] = index
                ranking_dict['events'][event].append(comp.wca_id)
        return ranking_dict


    def build(self):
        """ Build our results base """
        comp_filter = r"\t" + self.country + r"\t.*\t" + self.year + r"\t"
        # Filter only competitions in 'country' during 'year'
        # FIXME if someone really wants to use this under windows, this
        # should be "pythonified"
        grep_cmd = ["grep", "-P", comp_filter, COMPETITIONS_FILE]
        for line in subprocess.check_output(grep_cmd).split("\n"):
            if len(line) <= 0:
                continue
            fields = line.split("\t")
            self.competitions.append(Competition(fields[0], fields[6], fields[7]))

        self.competitions.sort()

        grep_cmd = ["grep"]
        # Filter only relevant competitions in results
        for comp in self.competitions:
            grep_cmd += ["-e", comp.cid]
        grep_cmd += [RESULTS_FILE]
        # Let's build our complete "database"
        for results in subprocess.check_output(grep_cmd).split("\n"):
            # We decode utf-8 because of non-english names
            # The json encoder is in charge of re-encoding the stuff
            fields = results.decode("utf-8").split("\t")
            if len(results) <= 0:
                continue
            event_id = fields[1]
            if event_id not in EVENTS:
                continue
            comp_id = fields[0]
            wca_id = fields[7]
            name = fields[6]
            if wca_id not in self.competitors:
                # A new competitor !
                self.competitors[wca_id] = Competitor(wca_id, name)
            current_competitor = self.competitors[wca_id]
            round_id = fields[2]
            position = fields[3]
            single = fields[4]
            average = fields[5]
            # Find the corresponding Competition object
            current_comp = next(x for x in self.competitions if x.cid == comp_id)
            # Add the current comp
            current_competitor.add_competition(current_comp)
            # Add the current result
            current_comp.add_result(event_id, Result(current_competitor, position, round_id),
                                    single, average)


if __name__ == "__main__":
    try:
        with open("points.json", "r") as fpoints:
            # Load points table from json
            SCORE_TABLE = json.load(fpoints)
        RGEN = RankingGenerator(COUNTRY, YEAR)
        RGEN.build()
        # Output the generated rankings
        with open(BUILD_DIR + "rankings.json", "w") as output:
            json.dump(RGEN.to_json(), output)

    except subprocess.CalledProcessError as exep:
        print "File doesn't exist or couldn't find competitions in France in " + YEAR

