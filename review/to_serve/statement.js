Array.prototype.remove = function() {
    var what, a = arguments, L = a.length, ax;
    while (L && this.length) {
        what = a[--L];
        while ((ax = this.indexOf(what)) !== -1) {
            this.splice(ax, 1);
        }
    }
    return this;
};

var app = angular.module('reviewApp',['ui.slider', 'ui.bootstrap', 'ngStorage']);

app.controller("StatementCtrl", function ($scope, $timeout, $http, $localStorage, $sessionStorage) {
    $scope.initdata = function() {
        $scope.$storage = $localStorage;
        $scope.location = window.location;
        var urlpseudo = $scope.parseQueryString(location.search.substring(1));
        if ('pseudo' in $scope.$storage && Object.keys(urlpseudo)[0] == $scope.$storage.pseudo){
            // Initialize scope data from local storage
            $scope.pseudo = $scope.$storage.pseudo;
            $scope.extracted = $scope.$storage.extracted;
            $scope.inferred = $scope.$storage.inferred;
            $scope.missing = $scope.$storage.missing;
            $scope.currentPage = $scope.$storage.currentPage;
            $('#loader').fadeOut(513, function(){
                $('#loader').remove();
            });
        } else {
            // Initialize scope data from server
            $http.get('/statements'+location.search).success(function(response){
                $scope.pseudo = response['pseudo'];
                $scope.extracted = response['extracted'];
                $scope.inferred = response['inferred'];
                $scope.missing = [];
                $scope.currentPage = 0;
                angular.forEach($scope.extracted, function(value, key){
                    value.correct = true;
                });
                $('#loader').fadeOut(513, function(){
                    $('#loader').remove();
                });
            }).error(function(response, status){
                    $('#loadmsg').text("Loading Failed: HTTP Status "+status)
                });
        }
    };
    $scope.parseQueryString = function( queryString ) {
        var params = {}, queries, temp, i, l;
        // Split into key/value pairs
        queries = queryString.split("&");
        // Convert the array of strings into an object
        for ( i = 0, l = queries.length; i < l; i++ ) {
            temp = queries[i].split('=');
            params[temp[0]] = temp[1];
        }
        return params;
    };
    // Sync data with localStorage
    $scope.syncCountdown = 20;
    $scope.syncLocal = function() {
        $scope.$storage.pseudo = $scope.pseudo;
        $scope.$storage.extracted = $scope.extracted;
        $scope.$storage.inferred = $scope.inferred;
        $scope.$storage.missing = $scope.missing;
        $scope.$storage.currentPage = $scope.currentPage;
        $scope.syncCountdown = 10;
        // Keep calling this function every 10 seconds
        $timeout($scope.syncLocal, 10000);
    };
    $timeout($scope.syncLocal, 20000);
    $timeout(function ctdSecond(){
        $scope.syncCountdown -= 1;
        $timeout(ctdSecond, 1000);
    }, 1000);


    /* Toggle the correctness of a topic */
    $scope.toggleCorrect = function(value){
        value.correct = !value.correct;
    };

    /* Return only correct statements of which lvls should be judged*/
    $scope.filterCorrect = function(statements){
        var out_statements = [];
        for(obj in statements) {
            if (statements[obj].correct && statements[obj].judge_lvl) {
                out_statements.push(statements[obj]);
            }
        }
        return out_statements;
    };
    /* Pagination */
    $scope.calcPageSize = function() {
        var width = $(window).width();
        var pageSize = 9;
        if (width > 1320){ pageSize = 12; }
        if (width > 1630){ pageSize = 15; }
        return pageSize
    }
    $scope.pageSize = $scope.calcPageSize();
    $scope.numberOfPages = function(statements){
        return Math.ceil($scope.filterCorrect(statements).length/$scope.pageSize);
    };
    $scope.incr = function(number, constant){
        $scope[number] += constant;
    };
    $scope.decr = function(number, constant){
        $scope[number] -= constant;
    };

    /* Add missing statements */
    $scope.getSkills = function(value) {
        return $http.get('/skill?query=' + value).then(function(response){
            return response.data.resultList;
        });
    };
    $scope.addMissing = function(toadd){
        $scope.missing.push(toadd);
        $scope.selected = "";
    };
    $scope.delMissing = function(todelete){
        $scope.missing.remove(todelete);
    };

    /* Save reviewed statements / topics */
    $scope.toServer = function(usrsubmit){
        var postjson = {'last_page': $scope.currentPage, 'pseudo': $scope.pseudo,
                        'extracted': $scope.extracted, 'inferred': $scope.inferred, 'missing': $scope.missing};
        console.log(postjson);
        ltime = new Date().getTime();
        $http.post('/'+$scope.pseudo+ltime, postjson).success(function(response){
            if ('success' in response && usrsubmit==true){
                var clear_bool = confirm("Sending successful! Delete the backup in your browser? Recommended on public computers.");
                if (clear_bool==true){
                    $scope.syncLocal = function(){
                        console.log("No more autosaving to localStorage.");
                    }
                    $localStorage.$reset();
                    $timeout($localStorage.$reset, 10000);
                }
            }
        }).error(function(){
            if (usrsubmit==true){
                alert("Saving to the server failed. Please send an email to alex@olieman.net, mentioning the current time.");
            }
        });
    };
    /* Auto-POST every 7 minutes */
    $scope.autoPost = function(){
        $scope.toServer(false);
        $timeout($scope.autoPost, 420000);
    }
    $timeout($scope.autoPost, 420000);
});

// A startFrom filter
app.filter('startFrom', function() {
    return function(input, start) {
        start = +start; //parse to int
        return input.slice(start);
    }
});