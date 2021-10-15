from hungerDataStructs import *

from datetime import datetime as dt
import os
from profilehooks import profile, coverage
from statistics import pstdev
from numpy import percentile as pct

class Solver:
    def __init__(self, metricID, numDist):
        Logger.initialize()
        self.reset(metricID, numDist)

    def __del__(self):
        Logger.cleanup()

    # External Getters ----------------------------------------------------------------------------

    def reset(self, metricID, numDist):
        if isinstance(metricID, str):
            self.metricID = metricID
        elif isinstance(metricID, int):
            self.metricID = allowed[metricID]
        self.placements = {region: 0 for region in sorted(regionlist.values(), key=lambda region: region.code)}
        self.districts = [District(i+1) for i in range(numDist)]

        # Time logging
        self.failures = 0
        self.startTime = 0
        self.lastTime = 0
        self.times = {}
        self.occurred = self.times.copy()

        # Calculate the minimum acceptable standard deviation
        maxRegionMetric = next(self.__getLargestUnplacedFor()).metrics[self.metricID]
        allOtherMetrics = sum(region.metrics[self.metricID] for region in self.__getUnplacedRegions()) - maxRegionMetric
        if numDist <= 1 or allOtherMetrics/(numDist-1) > maxRegionMetric:
            self.minAcceptable = 0.5
        else:
            hypothetical = [maxRegionMetric] + [allOtherMetrics/(numDist-1)]*(numDist-1)
            percentile = 100*pstdev(hypothetical)/sum(hypothetical)
            self.minAcceptable = max(0.5, percentile)

    def isSolved(self):
        return all(placement != 0 for placement in self.placements.values()) #and self.getStandardDevAsPercent() < self.minAcceptable

    def getStandardDevAsPercent(self):
        metrics = [district.metric for district in self.districts]
        return 100*pstdev(metrics)/sum(metrics)

    def getTimeSinceStarted(self):
        if self.startTime == 0:
            return -1
        else:
            return(dt.now() - self.startTime).total_seconds()

    def getEmptyDataFrame():
        return {new_list: [] for new_list in ["region","code","district","metric"]}

    def getDummyDataFrame():
        result = Solver.getEmptyDataFrame()

        result["region"].append("none")
        result["code"].append("none")
        result["district"].append(str(1))
        result["metric"].append("none")

        return result

    def getCurrentDataFrame(self):
        result = Solver.getEmptyDataFrame()

        for district in self.districts:
            for region in district.regions:
                result["region"].append(region.name)
                result["code"].append(region.code)
                result["district"].append(str(district.index))
                result["metric"].append(region.metrics[self.metricID])

        if len(result["region"]) == 0:
            result = Solver.getDummyDataFrame()

        return result

    # Printers ------------------------------------------------------------------------------------

    def printResult(self):
        Logger.l("\n\n+---------------------------------------------------------+")

        for district in self.districts:
            print("District {} ({}):".format(district.index, district.metric))
            print("|".join(sorted(region.code for region in district.regions)))
            print()

        return self

    def printConcise(self):
        placedRegions = list(self.__getPlacedRegions())
        formatstr = "|".join(["{:^" + str(len(placedRegions[0].code)) + "}"]*len(placedRegions))
        print(formatstr.format(*(region.code for region in placedRegions)))
        print(formatstr.format(*(self.placements[region] for region in placedRegions)))

        return self

    def __doStepLogging(self):
        total = sum(self.times.values())
        total = 1 if total == 0 else total
        #timesToPrint = { key: time for key, time in sorted(self.times.items()) if key in [] }
        timesToPrint = { key: time for key, time in sorted(self.times.items()) }
        result = []

        # Failure count
        result.append("failures")
        result.append("")
        result.append(self.failures)

        # Time so far
        result.append("total")
        result.append("")
        result.append(self.getTimeSinceStarted())

        # Times
        for key, time in timesToPrint.items():
            result.append(key)
            result.append(self.occurred[key])

            percent = 100*time/total
            if percent > 70:
                result.append(color.RED)
            elif percent > 20:
                result.append(color.YELLOW)
            else:
                result.append(color.GREEN)
            result.append(percent)

        # Put it all together
        formatStr = " | ".join(["{}: {}{:<6}" + Style.RESET_ALL] + ["{}: {}{:7.3f}" + Style.RESET_ALL] + ["{}({:4}):{}{:6.2f}%" + Style.RESET_ALL]*len(timesToPrint))
        resultStr = formatStr.format(*result)
        # Subtract out the hidden style characters
        numChars = len(resultStr) - 9 * len(timesToPrint)

        # Progress bar
        # The number of available cells for progress bar
        availCells = os.get_terminal_size().columns - numChars - 14
        # The number we'll actually use - closest 10, rounding down (no rounding if less than 10)
        numCells = availCells if availCells <= 10 else availCells - (availCells%10)

        if numCells > 5:
            percent = 100*len(list(self.__getPlacedRegions()))/len(self.placements)
            if percent < 50:
                progressColor = color.RED
            elif percent < 90:
                progressColor = color.YELLOW
            else:
                progressColor = color.GREEN
            progressbar = ("completion: {}+{:" + "{}".format(numCells) + "}+" + Style.RESET_ALL + " | ").format(progressColor, "="*round(percent*(numCells/100)))
            suffix = ""
        else:
            progressbar = ""
            suffix = (os.get_terminal_size().columns - numChars)*" "

        # Put it all together!
        print(progressbar + resultStr + suffix, end="\r")

    # Setters -------------------------------------------------------------------------------------

    def __place(self, region, district):
        district.addRegion(region, self.metricID)
        self.placements[region] = district.index

    def __unplace(self, region):
        district = self.districts[self.placements[region]-1]
        district.removeRegion(region, self.metricID)
        self.placements[region] = 0
        return {region.code: {district.index}}

    def __updateTime(self, tag = None):
        if not tag:
            self.lastTime = dt.now()
        else:
            newTime = dt.now()
            self.times[tag] = self.times.get(tag, 0) + (newTime - self.lastTime).total_seconds()
            self.occurred[tag] = self.occurred.get(tag, 0) + 1
            self.lastTime = newTime

    def __addToFailures(result, failures):
        for code, indexSet in result.items():
            failures[code] = failures.get(code, set()) | indexSet

        return failures

    # Generators ----------------------------------------------------------------------------------

    doOrderInspection = False

    def __getLargestUnplacedFor(self, district=None):
        if district==None:
            unplaced = [region for region in self.__getUnplacedRegions()]
            sorter = lambda region: region.metrics[self.metricID]
            # Inspect the ordering
            if Solver.doOrderInspection:
                print("Getting all unused regions from {}".format(list(self.__getUnplacedRegions())))
                fmtString = "\t{}:\tMetric: {}"
                for region in unplaced:
                    print(fmtString.format(region, region.metrics[self.metricID]))
        else:
            unplaced = [region for region in self.__getUnplacedRegions() if region.code in district.adj or len(region.adj) == 0]
            sorter = lambda region: (district.adj.get(region.code,0), region.metrics[self.metricID])
            # Inspect the ordering
            if Solver.doOrderInspection:
                print("Getting regions adjacent to District {} from {}".format(district.index, list(self.__getUnplacedRegions())))
                fmtString = "\t{}:\tNumber of adjacent in district: {}\tMetric: {}"
                for region in unplaced:
                    print(fmtString.format(region, district.adj.get(region.code,0), region.metrics[self.metricID]))

        while region := max(unplaced, key=sorter, default=False):
            yield region
            unplaced.remove(region)

    def __getNextStarter(self):
        # Get the distances
        minDistances = {}
        percentile = pct([region.metrics[self.metricID] for region in self.__getUnplacedRegions()], 50)
        for region in filter(lambda region: region.metrics[self.metricID] >= percentile, self.__getUnplacedRegions()):
            reachablePlacedRegions = { inRegion: distanceMatrix[region][inRegion] for inRegion in self.__getPlacedRegions() if distanceMatrix[region][inRegion] > 0 }
            minDistances[region] = min(reachablePlacedRegions.items(), key=lambda item: item[1], default=("", float("inf")))

        # If nothing is reachable, just get the biggest unused region
        if all(distance[1] == float("inf") for distance in minDistances.values()):
            if Solver.doOrderInspection:
                print("Cannot reach any of the placed regions in {}!".format(list(self.__getPlacedRegions()), region.code))

            for region in self.__getLargestUnplacedFor():
                yield region

        # If we can reach some items, get those items!
        else:
            if Solver.doOrderInspection:
                print("Getting starters from {}".format(list(self.__getUnplacedRegions())))
                fmtString = "\t{}:\tShortest distance to neighbor: {}"
                for region in sorted(filter(lambda code: minDistances[code][1] != float("inf"), minDistances), key=lambda code: minDistances[code][1], reverse=True):
                    print(fmtString.format(region, minDistances[region.code][1]))

            for region in sorted(minDistances, key=lambda code: minDistances[code][1], reverse=True):
                yield region

    def __getUnusedDistricts(self):
        # Group unused regions into districts
        regionsToBePlaced = sorted(self.__getUnplacedRegions(), key=lambda region: len(region.adj))
        while seedRegion := next(iter(regionsToBePlaced), False):
            unusedDistrict = District(0)
            unusedDistrict.addRegion(seedRegion, self.metricID)
            regionsToBePlaced.remove(seedRegion)

            while adjRegion := next(filter(lambda region: region.code in unusedDistrict.adj, regionsToBePlaced), False):
                unusedDistrict.addRegion(adjRegion, self.metricID)
                regionsToBePlaced.remove(adjRegion)

            yield unusedDistrict

    def __getBorders(self):
        for district in self.districts:
            adjUnplaced = [region for region in self.__getUnplacedRegions() if region.code in district.adj]
            while seedRegion := next(iter(adjUnplaced), False):
                border = District(0)
                border.addRegion(seedRegion, self.metricID)
                adjUnplaced.remove(seedRegion)

                while adjRegion := next(filter(lambda region: region.code in border.adj, adjUnplaced), False):
                    border.addRegion(adjRegion, self.metricID)
                    adjUnplaced.remove(adjRegion)

                if all(code in district.regions for code in border.adj):
                    yield district, border

    def __getEnclosedRegions(self):
        for ud in self.__getUnusedDistricts():
            adjacentSet = set(ud.adj)
            for district in self.districts:
                # If this unused district's adjacent regions are all in the district, AND there are some adjacent regions (sorry Alaska), add them all!
                if adjacentSet and adjacentSet <= district.regions:
                    Logger.s("!", district.index, "enclosed {} regions:".format(len(ud.regions)), ud.regions)
                    for region in ud.regions:
                        yield region, district

    def __getPlacedRegions(self):
        for region in filter(lambda region: self.placements[region] != 0, self.placements):
            yield region

    def __getUnplacedRegions(self):
        for region in filter(lambda region: self.placements[region] == 0, self.placements):
            yield region

    # Solve it ------------------------------------------------------------------------------------

    def doStep(self, region=None, district=None, doStatus=False):
        # Ensure that inputs and data structures are initialized
        if district is None:
            district = min(self.districts)
        if region is None:
            region = next(self.__getLargestUnplacedFor())

        regionsToRemove = []
        failures = {}

        self.__updateTime()

        # Add this region to this district
        self.__place(region, district)
        regionsToRemove.append(region)

        self.__updateTime("addRegion")

        # Get the unused districts
        if all(len(district.adj) > 0 for district in self.districts):
            for enclosedRegion, enclosingDistrict in self.__getEnclosedRegions():
                # If one of the enclosed regions was already part of a failure state, we failed!
                if enclosingDistrict.index in failures.get(enclosedRegion.code, []):
                    return failures
                self.__place(enclosedRegion, enclosingDistrict)
                regionsToRemove.append(enclosedRegion)

        self.__updateTime("getUnused")

        # Do logging and reset the timer to account for how slow it is
        if Solver.doOrderInspection: print("Adding {} to {}, enclosing {}".format(region, district.index, [enclosedRegion for enclosedRegion in regionsToRemove if enclosedRegion != region]))
        if doStatus:        self.__doStepLogging()
        self.__updateTime()

        # Return no failures if it's solved!
        if self.isSolved():
            return {}

        self.__updateTime("checkSolved")

        # Get the smallest district
        nextDistrict = min(self.districts)

        self.__updateTime("getMinDistrict")

        # Get the generator for this state
        if len(nextDistrict.adj) == 0:
            # seed - there are no adjacent regions available
            regions = self.__getNextStarter()
            self.__updateTime("makeSeed")
        else:
            # largest adjacent region, or largest neighborless region
            regions = self.__getLargestUnplacedFor(nextDistrict)
            self.__updateTime("makeUnplaced")

        # For each possible next candidate, test that subtree
        for nextRegion in filter(lambda region: nextDistrict.index not in failures.get(region.code, []), regions):
            self.__updateTime("getNextRegion")
            if (result := self.doStep(nextRegion, nextDistrict, doStatus=doStatus)) == {}:
                return {}
            else:
                failures = Solver.__addToFailures(result, failures)
            self.__updateTime()

        # Do logging and reset the timer to account for how slow it is
        if Solver.doOrderInspection: print("Failed to add {} to {}, enclosing {}".format(region, district.index, [enclosedRegion for enclosedRegion in regionsToRemove if enclosedRegion != region]))
        self.__updateTime()

        # None of them worked! Undo this step and try the next at the tier above this
        for removalRegion in regionsToRemove:
            Solver.__addToFailures(self.__unplace(removalRegion), failures)

        self.__updateTime("removeRegion")

        self.failures += 1
        return failures

    def solve(self, doStatus = False, doLogging = False):
        Logger.doLogging = doLogging
        # Don't show the progress bar if logging is enabled
        if doLogging:   doStatus = False
        if doStatus:    self.startTime = dt.now()

        for region in self.__getNextStarter():
            if self.doStep(region, self.districts[0], doStatus=doStatus) == {}:
                if doStatus:
                    print()
                    print("\t{:>10}({}) took {}s ({:.3f}%)".format(self.metricID, len(self.districts), self.getTimeSinceStarted(), self.getStandardDevAsPercent()))
                return self

        print(color.RED + "Something's wrong!!!" + Style.RESET_ALL)
        return self

# Solve and unit test

import cProfile
import pstats

def profile(string):
    filename = "stats.profile"
    cProfile.run(string, filename)
    stats = pstats.Stats(filename)
    stats.strip_dirs()
    stats.sort_stats("tottime")
    stats.print_stats(10)

def unitTest(count, doStatus=True):
    solver = Solver(0, 1)
    result = {new_list: [] for new_list in allowed}
    for count in range(1, count + 1):
        if doStatus: print("{} districts".format(count))
        for metric in allowed:
            tick = dt.now()
            solver.reset(metric, count)
            solver.solve(doStatus)
            result[metric].append((dt.now() - tick).total_seconds())
        if doStatus: print()

    # Write to file
    i = 0
    while os.path.exists("logs/log{}.txt".format(i)):
        i += 1

    metricFmt = "{:>13} |"
    intFmt = " | ".join(["{:^9}"]*count)+"\n"
    floatFmt = " | ".join(["{:^9.3f}"]*count)+"\n"
    with open("logs/log{}.txt".format(i), "w", encoding='utf8') as log:
        log.write((metricFmt.format("") + intFmt.format(*range(1,count + 1))))
        for metric, values in result.items():
            log.write((metricFmt.format(metric) + floatFmt.format(*values)))

for count in range(4, 10):
    for metric in allowed:
        Solver(metric, count).solve(True)

#unitTest(6)
#profile("Solver(4, 3).solve().printConcise()")
#Solver(1, 4).solve().printResult().printConcise()