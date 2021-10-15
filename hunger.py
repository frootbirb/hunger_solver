from hungerDataStructs import *

from datetime import datetime as dt, date
import os
from statistics import pstdev
from numpy import percentile as pct, sqrt

class Solver:
    def __init__(self, metricID, numDist):
        Logger.initialize()
        self.reset(metricID, numDist)

    def __del__(self):
        Logger.cleanup()

    def reset(self, metricID, numDist):
        # Enable MetricID to be set as a string or an index
        if isinstance(metricID, str):
            self.metricID = metricID
        elif isinstance(metricID, int):
            self.metricID = allowed[metricID]
        
        self.inProgress = False

        # We have three ways of tracking region state... sad but fast!
        self.placements = { region: 0 for region in sorted(regionlist.values(), key=lambda region: region.code) }
        self.placedRegions = []
        self.unplacedRegions = { region: region for region in regionlist.values() }

        # A list of the unused districts, to make enclosure detection reasonably fast
        self.unusedDistricts = list(self.__getUnusedDistrictsFor(list(regionlist.values())))

        # This helps prevent us from retreading our failed past attempts
        self.failures = set()

        # Logging helpers
        self.startTime = 0
        self.lastTime = 0
        self.times = {}
        self.occurred = {}
        Logger.logDepth = ""

        # Calculate the maximum district size
        sumAll = sum(region.metrics[self.metricID] for region in regionlist.values())
        if numDist > 1:
            # shorthands for mathematical clarity
            m = sumAll/numDist
            s = sumAll
            n = numDist

            '''
            Doing out my work
            l = Large; what we're solving for, the maximum possible district size that allows a 0.5% std dev

            0.5 = 100*stddev/s
            s/200 = stddev = sqrt(((n/2)* (l - m)**2 + (n/2)*((s - l*(n/2))/(n/2) - m)**2)/n)
            s**2/40000 =          ((n/2)* (l - m)**2 + (n/2)*((s - l*(n/2))/(n/2) - m)**2)/n
            n*s**2/40000 =         (n/2)* (l - m)**2 + (n/2)*((s - l*(n/2))/(n/2) - m)**2
            n*s**2/40000 =         (n/2)*((l - m)**2 +          ((2*s/n - l)      - m)**2)
           (n*s**2/40000)/(n/2) =         (l - m)**2 +          ((2*s/n - l)      - m)**2
            s**2/20000 =              l**2 - 2*m*l + m**2 +      (2*s/n - m - l      )**2
            s**2/20000 =              l**2 - 2*m*l + m**2 +      (2*s/n - m)**2 - 2*(2*s/n - m)*l + l**2
            s**2/20000 =              l**2 + l**2 - 2*m*l - (4*s/n - 2*m)*l + m**2 + (2*s/n - m)**2
            s**2/20000 =              2*l**2 -     (2*m + (4*s/n - 2*m))*l  + m**2 + (2*s/n - m)**2
            0 =                       2*l**2 -     (2*m + 4*s/n - 2*m)*l    + m**2 + (2*s/n - m)**2 - s**2/20000
            '''

            # solving the quadratic equation
            a = 2
            b = 2*m + 4*s/n - 2*m
            c = m**2 + (2*s/n - m)**2 - s**2/20000
            d = sqrt((b**2) - (4*a*c))
            posMaxForHalfPercent = abs((-b+d)/(2*a))
            negMaxForHalfPercent = abs((-b-d)/(2*a))

            # Get the largest single region - we can't expect to make districts smaller than this!
            maxRegionMetric = self.__getLargestUnplacedFor().metrics[self.metricID]

            # Whichever solution is larger, or the largest single region if it's larger than the solution
            self.maxAcceptableMetric = max(posMaxForHalfPercent, negMaxForHalfPercent, maxRegionMetric)
        else:
            # If there is only one district, there is no std dev!
            self.maxAcceptableMetric = sumAll

        # Create the districts
        self.districts = [District(i+1, self.metricID, self.maxAcceptableMetric) for i in range(numDist)]

    def __getstate__(self):
        state = self.__dict__.copy()
        state['placements'] = { region.code: placement for region, placement in self.placements.items() }
        state['unplacedRegions'] = [ region.code for region in self.unplacedRegions ]
        return state
    
    def __setstate__(self, newstate):
        newstate['placements'] = { regionlist[code]: placement for code, placement in newstate['placements'].items() }
        newstate['unplacedRegions'] = { regionlist[code]: regionlist[code] for code in newstate['unplacedRegions'] }
        newstate['unusedDistricts'] = list(self.__getUnusedDistrictsFor(list(newstate['unplacedRegions'])))
        self.__dict__.update(newstate)

    # External Getters ----------------------------------------------------------------------------
    
    def isSolved(self):
        return all(placement > 0 for placement in self.placements.values()) and all(district.metric <= self.maxAcceptableMetric for district in self.districts)

    def getStandardDevAsPercent(self):
        metrics = [ district.metric for district in self.districts ]
        sumAll = sum(metrics)
        return 0 if sumAll == 0 else 100*pstdev(metrics)/sumAll

    def getTimeSinceStarted(self):
        if self.startTime == 0:
            return -1
        else:
            return (self.lastTime - self.startTime).total_seconds()

    def getEmptyDataFrame():
        return { new_list: [] for new_list in ["region","code","district","metric"] }

    def getDummyDataFrame():
        return { new_list: ["none"] for new_list in ["region","code","district","metric"] }

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

    def getStarters(self, doStatus = False):
        # Get the starter regions for all districts - this is mostly for logging!
        while any(len(district.regions) == 0 for district in self.districts):
            self.doStep(doStatus=doStatus)
        return self

    # Printers ------------------------------------------------------------------------------------

    def printResult(self):
        for district in self.districts:
            print("District {} ({}):".format(district.index, district.metric))
            print("|".join(sorted(region.code for region in district.regions)))
            print()

        return self

    def printConcise(self):
        placedRegions = sorted(self.placedRegions, key=lambda region: region.code)
        formatstr = "|".join(["{:^" + str(len(placedRegions[0].code)) + "}"]*len(placedRegions))
        print(formatstr.format(*(region.code for region in placedRegions)))
        print(formatstr.format(*(self.placements[region] for region in placedRegions)))

        return self

    def printSummary(self):
        fmt = "\t{:>10}({}) took {:.3f}s ({:.3f}%, {} failures)"
        print(fmt.format(self.metricID,
              len(self.districts),
              self.getTimeSinceStarted(),
              self.getStandardDevAsPercent(),
              len(self.failures)))

        return self

    def __doStepLogging(self):
        total = sum(self.times.values())
        total = 1 if total == 0 else total
        timesToPrint = { key: time for key, time in sorted(self.times.items()) }
        result = []

        # Failure count
        result.append("failures")
        result.append(len(self.failures))

        # Time so far
        result.append("total")
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
        formatStr = " | ".join(["{}: {:<6}"] + ["{}: {:7.3f}"] + ["{}({:4}):{}{:6.2f}%" + Style.RESET_ALL]*len(timesToPrint))
        resultStr = formatStr.format(*result)
        # Subtract out the hidden style characters
        numChars = len(resultStr) - 9 * len(timesToPrint)

        # Progress bar
        # The number of available cells for progress bar
        availCells = os.get_terminal_size().columns - numChars - 7
        # The number we'll actually use - closest 10, rounding down (no rounding if less than 10)
        numCells = availCells if availCells <= 10 else availCells - (availCells%10)

        if numCells > 5:
            percent = 100*len(self.placedRegions)/len(self.placements)
            if percent < 50:
                progressColor = color.RED
            elif percent < 90:
                progressColor = color.YELLOW
            else:
                progressColor = color.GREEN
            progressbar = (" {}+{:" + "{}".format(numCells) + "}+" + Style.RESET_ALL + " | ").format(progressColor, "="*round(percent*(numCells/100)))
            suffix = ""
        else:
            progressbar = ""
            suffix = (os.get_terminal_size().columns - numChars-1)*" "

        # Put it all together!
        print(progressbar + resultStr + suffix, end="\r")

    # Setters -------------------------------------------------------------------------------------

    def __addToFailures(self):
        self.failures.add(tuple(self.placements.values()))

    def __place(self, region, district):
        # Add to the four different tracking methods (gross)
        district.addRegion(region)
        self.placedRegions.append(region)
        self.unplacedRegions.pop(region)
        self.placements[region] = district.index

        # Look up which unused district this one is in
        for uDistrict in self.unusedDistricts:
            if region in uDistrict.regions:
                isOnlyConnection = not uDistrict.canRemove(region)
                uDistrict.removeRegion(region)

                if len(uDistrict.regions) == 0:
                    self.unusedDistricts.remove(uDistrict)
                # If this is true, this region was the only thing holding two parts of the district together
                # we have to regenerate new districts after removal, since it's (probably) been split
                elif isOnlyConnection:
                    self.unusedDistricts.remove(uDistrict)
                    for newDistrict in self.__getUnusedDistrictsFor(uDistrict.regions):
                        self.unusedDistricts.append(newDistrict)
                break

    def __unplace(self, region = None):
        # Remove from the four different tracking methods (gross)
        if region:
            self.placedRegions.remove(region)
        else:
            region = self.placedRegions.pop()
        self.unplacedRegions[region] = region
        district = self.districts[self.placements[region]-1]
        district.removeRegion(region)
        self.placements[region.code] = 0

        adjDists = [ uDistrict for uDistrict in self.unusedDistricts if region.code in uDistrict.adj ]
        # This is adjacent to exactly one unused district - just add to that one
        if len(adjDists) == 1:
            adjDists[0].addRegion(region)
        # This is not adjacent to any unused districts - it's a new, lonely district all on its lonesome
        elif len(adjDists) == 0:
            uDistrict = District(0)
            uDistrict.addRegion(region)
            self.unusedDistricts.append(uDistrict)
        else:
            # This is adjacent to multiple unused districts - we can merge them!
            adjDists.sort(key=lambda uDist: len(uDist.regions))
            uDistrict = adjDists.pop()
            uDistrict.addRegion(region)

            # Merge the regions from all adjacent districts into this district
            for adjRegion in (region for regions in (uDistrict.regions for uDistrict in adjDists) for region in regions):
                uDistrict.addRegion(adjRegion)

            # Remove the now-superfluous districts
            self.unusedDistricts = [uDistrict for uDistrict in self.unusedDistricts if uDistrict not in adjDists]

        return region, district

    def __unplaceSmarter(self):
        district = min(self.districts)

        # Get the difference between the number of neighbors in this and the number of neighbors in the current district
        diffCalc = lambda region: district.adj.get(region, 0) - sum(1 for adjCode in region.adj if adjCode in self.districts[self.placements[region]-1].regions)

        # Get the max placed region adjacent to this district which is eligible to be added and at least as connected to this as it is to the district it's leaving
        while not (region := max((region for region in self.placedRegions if self.__canAddToDistrict(region, district) and self.districts[self.placements[region]-1].canRemove(region)),
                                 key=lambda region: (district.adj.get(region, 0), diffCalc(region), region.metrics[self.metricID]),
                                 default=False)):
            # While we can't find one, just unplace the last placed region
            self.__unplace()
            district = min(self.districts)

        self.__unplace(region)

        return region, district

    def __updateTime(self, tag = None):
        # Initialize the start time, if we have to
        if self.startTime == 0:
            self.startTime = dt.now()

        # Initialize the last time if no tag was provided
        if not tag:
            self.lastTime = dt.now()
        else:
            newTime = dt.now()
            self.times[tag] = self.times.get(tag, 0) + (newTime - self.lastTime).total_seconds()
            self.occurred[tag] = self.occurred.get(tag, 0) + 1
            self.lastTime = newTime

    def __addUnusedDistricts(self):
        # Copy the unused districts, since we remove things while traversing
        tempUnused = self.unusedDistricts[:]
        for uDistrict in tempUnused:
            adjacentSet = set(uDistrict.adj)
            for district in self.districts:
                # If this unused district's adjacent regions are all in district, AND this unused district has some adjacent regions (sorry Alaska), add them all!
                if adjacentSet and adjacentSet <= district.regions:
                    regionsToPlace = []
                    # Check if these regions can be added to the district in question
                    # We already know they are adjacent, so we only need to check if this is on the failures list
                    for region in uDistrict.regions:
                        if not self.__canAddToDistrict(region, district, onlyFailures=True):
                            return False
                        regionsToPlace.append(region)

                    Logger.s("!", district.index, "enclosed {} regions:".format(len(regionsToPlace)), regionsToPlace)
                    for region in regionsToPlace:
                        self.__place(region, district)

                    # We have placed all the items from this district - the last __place removed it from the list
                    break

        return True

    # Internal getters ----------------------------------------------------------------------------

    def __isInDisconnectedDistrict(self, region):
        for district in (district for district in self.unusedDistricts if len(district.adj) == 0):
            if region in district.regions:
                return True

        return False

    def __canAddToDistrict(self, region, district, onlyFailures=False, allowDisconnected=True):
        # If we aren't only checking failures, confirm that:
        # we can add the region to the district (metric would not overflow district size)
        # the region is either adjacent, or the district has no neighbors, or the region is in a disconnected unused district
        if not onlyFailures and not (district.canAdd(region) and (district.isAdjacent(region) or (allowDisconnected and self.__isInDisconnectedDistrict(region)))):
            return False
            
        # Short-circuit evaluation if there are no failures! we're guaranteed to not find it
        if len(self.failures) == 0:
            return True

        # Check if the state post-placement has been tried and failed before
        priorIndex = self.placements[region]
        self.placements[region] = district.index
        isFailure = tuple(self.placements.values()) in self.failures
        self.placements[region] = priorIndex
        return not isFailure

    def __getDistanceScore(self, region, district):
        distances = [ region.distances.get(inRegion, 0) for inRegion in district.regions ]
        return -sum(distances) if distances else 1

    def __getLargestUnplacedFor(self, district=None):
        if district==None:
            # Gets the biggest unplaced region, no other criteria
            return max(self.unplacedRegions,
                       key=lambda region: region.metrics[self.metricID],
                       default=False)
        else:
            # True if there are any non-placed adjacent districts
            anyAdjacent = any(self.placements[adjCode] <= 0 for adjCode in district.adj)
            # Get the largest unplaced region which can be added to this district, keyed first on closest region and second on metric size
            return max((region for region in self.unplacedRegions if self.__canAddToDistrict(region, district, allowDisconnected=not anyAdjacent)),
                       key=lambda region: (self.__getDistanceScore(region, district),
                                          region.metrics[self.metricID]),
                       default=False)

    def __getNextStarter(self):
        # Get the distances
        minDistances = {}
        metrics = [region.metrics[self.metricID] for region in self.unplacedRegions]

        # If there are no regions to place, return False
        if len(metrics) == 0:
            return False

        percentile = pct(metrics, 50)
        district = min(self.districts)
        for region in (region for region in self.unplacedRegions if region.metrics[self.metricID] >= percentile and self.__canAddToDistrict(region, district)):
            minDistances[region] = min((tuple for tuple in region.distances.items() if tuple[0] in self.placedRegions),
                                        key=lambda item: item[1],
                                        default=("", float("-inf")))

        # If nothing is reachable, just get the biggest unused region
        if all(distance[1] == float("-inf") for distance in minDistances.values()):
            return self.__getLargestUnplacedFor()

        # If we can reach some items, get those items!
        else:
            return max(minDistances, key=lambda region: (minDistances[region][1], region.metrics[self.metricID]), default=False)

    def __getUnusedDistrictsFor(self, regionsToBePlaced):
        # Group the provided regions into districts
        while seedRegion := next(iter(regionsToBePlaced), False):
            unusedDistrict = District(0)
            unusedDistrict.addRegion(seedRegion)
            regionsToBePlaced.remove(seedRegion)

            while adjRegion := next((regionlist[code] for code in unusedDistrict.adj if code in regionsToBePlaced), False):
                unusedDistrict.addRegion(adjRegion)
                regionsToBePlaced.remove(adjRegion)

            yield unusedDistrict

    # Solve it ------------------------------------------------------------------------------------

    def getNextRegion(self):
        self.__updateTime()

        # get the smallest district
        district = min(self.districts)

        self.__updateTime("getMinDistrict")

        # seed - there are no adjacent regions available
        if len(district.adj) == 0 and (region := self.__getNextStarter()):
            self.__updateTime("getSeed")
            return region, district
        # largest adjacent region, or largest neighborless region
        elif region := self.__getLargestUnplacedFor(district):
            self.__updateTime("getUnplaced")
            return region, district
        # else step backwards until we find something we can add to something else!
        else:
            self.__updateTime("selectFailed")
            # Whatever led us to this point failed us - record the failure
            self.__addToFailures()
            return False

    def doStep(self, doStatus = False):
        # Don't double-dip
        if self.inProgress:
            return

        self.inProgress = True

        self.__updateTime()

        # Don't perform this if it's solved
        if self.isSolved():
            return

        # If we can't place something...
        if not (tuple := self.getNextRegion()):
            # Unplace the previous one, and get the next region!
            self.__updateTime()
            tuple = self.__unplaceSmarter()
            self.__updateTime("unplace")

        self.__place(*tuple)

        self.__updateTime("place")

        # If all the districts have something adjacent to them, check for enclosed regions
        if all(len(district.adj) > 0 for district in self.districts) and not self.isSolved():
            if not self.__addUnusedDistricts():
                # Whatever led us to this point failed us - record the failure
                self.__addToFailures()
            self.__updateTime("checkUnused")

        # Do the logging for this step
        if doStatus:    self.__doStepLogging()

        self.inProgress = False

    def solve(self, doStatus = False, doLogging = False):
        Logger.doLogging = doLogging
        # Don't show the progress bar if logging is enabled
        if doLogging:   doStatus = False

        while not self.isSolved():
            self.doStep(doStatus)

        if doStatus:    print()

        return self